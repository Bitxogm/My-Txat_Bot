import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.api.dependencies import (
    get_app_settings,
    get_app_settings_repository,
    get_attachment_repository,
    get_conversation_repository,
    get_feedback_repository,
    get_file_storage,
    get_llm_provider,
    get_memory_repository,
    get_osint_source_repository,
    get_personality_repository,
)
from app.api.generation import context_for
from app.api.routes.chat import MAX_CONTENT_CHARS
from app.api.routes.personalities import PERSONALITY_ID_PATTERN
from app.api.streaming import stream_reply
from app.core.config import Settings
from app.core.errors import (
    AttachmentNotFoundError,
    BadRequestError,
    ConversationNotFoundError,
    ModelWithoutVisionError,
    PersonalityLockedError,
    PersonalityNotFoundError,
)
from app.domain.attachment import (
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_IMAGES_PER_REQUEST,
    Attachment,
)
from app.domain.chat import ImageData, Role
from app.domain.context import Turn, fit_history
from app.domain.conversation import (
    TITLE_MAX_CHARS,
    Conversation,
    Generation,
    MessageStatus,
    PersonalitySnapshot,
    StoredMessage,
    title_from_message,
)
from app.domain.feedback import Feedback, FeedbackReason, Rating
from app.domain.memory import Memory, format_memory_block
from app.domain.osint import format_osint_catalog, needs_osint_catalog
from app.domain.personality import DEFAULT_PERSONALITY_ID, Personality
from app.domain.prompts import BASE_PROMPT_VERSION, compose_system_prompt
from app.ports.attachments import AttachmentRepository
from app.ports.conversations import ConversationRepository
from app.ports.feedback import FeedbackRepository
from app.ports.file_storage import FileStorage
from app.ports.llm import LLMProvider
from app.ports.memories import AppSettingsRepository, MemoryRepository
from app.ports.osint_sources import OsintSourceRepository
from app.ports.personalities import PersonalityRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])

ConversationId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
Repo = Annotated[ConversationRepository, Depends(get_conversation_repository)]


class PersonalityRef(BaseModel):
    """The personality a conversation was created with (snapshot, read-only).

    `id` is null if that personality has since been deleted; name and icon are kept.
    """

    id: str | None
    name: str
    icon: str | None


class ConversationOut(BaseModel):
    id: str
    title: str
    model: str
    created_at: datetime
    updated_at: datetime
    personality: PersonalityRef | None

    @classmethod
    def of(cls, c: Conversation) -> "ConversationOut":
        snap = c.personality
        return cls(
            id=c.id,
            title=c.title,
            model=c.model,
            created_at=c.created_at,
            updated_at=c.updated_at,
            # Conversations from before personalities existed have no snapshot name.
            personality=(
                PersonalityRef(id=snap.id, name=snap.name, icon=snap.icon) if snap.name else None
            ),
        )


class MessageAttachment(BaseModel):
    id: str
    filename: str
    kind: str
    size_bytes: int
    truncated: bool


class MessageFeedback(BaseModel):
    """The rating of an assistant reply, as shown next to it."""

    rating: Rating
    reasons: list[FeedbackReason]
    correction: str | None

    @classmethod
    def of(cls, f: Feedback) -> "MessageFeedback":
        return cls(rating=f.rating, reasons=list(f.reasons), correction=f.correction)


class MessageOut(BaseModel):
    id: int
    role: Role
    content: str
    status: MessageStatus
    created_at: datetime
    attachments: list[MessageAttachment] = []
    feedback: MessageFeedback | None = None

    @classmethod
    def of(
        cls,
        m: StoredMessage,
        attachments: list[Attachment] | None = None,
        feedback: Feedback | None = None,
    ) -> "MessageOut":
        return cls(
            id=m.id,
            role=m.role,
            content=m.content,
            status=m.status,
            created_at=m.created_at,
            feedback=MessageFeedback.of(feedback) if feedback else None,
            attachments=[
                MessageAttachment(
                    id=a.id,
                    filename=a.filename,
                    kind=a.kind,
                    size_bytes=a.size_bytes,
                    truncated=a.truncated,
                )
                for a in attachments or []
            ],
        )


class ConversationList(BaseModel):
    conversations: list[ConversationOut]


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationPatch(BaseModel):
    # The title is always editable. The personality only while the conversation is a draft, with
    # no user message yet (ADR-022); after that its snapshot is fixed (ADR-013).
    model_config = ConfigDict(extra="forbid")

    title: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_CHARS),
        ]
        | None
    ) = None
    personality_id: str | None = Field(default=None, pattern=PERSONALITY_ID_PATTERN)

    @model_validator(mode="after")
    def _something_to_change(self) -> "ConversationPatch":
        if self.title is None and self.personality_id is None:
            raise ValueError("Indica title o personality_id")
        return self


AttachmentRef = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    # Files uploaded to this conversation and not sent yet (POST .../attachments).
    attachment_ids: list[AttachmentRef] = Field(
        default_factory=list, max_length=MAX_ATTACHMENTS_PER_MESSAGE
    )


Attachments = Annotated[AttachmentRepository, Depends(get_attachment_repository)]


def _by_message(attachments: list[Attachment]) -> dict[int, list[Attachment]]:
    grouped: dict[int, list[Attachment]] = {}
    for attachment in attachments:
        if attachment.message_id is not None:
            grouped.setdefault(attachment.message_id, []).append(attachment)
    return grouped


class NewConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, min_length=1, max_length=200)
    personality_id: str | None = Field(default=None, pattern=PERSONALITY_ID_PATTERN)


async def _require(repo: ConversationRepository, conversation_id: str) -> Conversation:
    conversation = await repo.get(conversation_id)
    if conversation is None:
        raise ConversationNotFoundError
    return conversation


def _snapshot_of(personality: Personality) -> PersonalitySnapshot:
    fields = personality.fields
    return PersonalitySnapshot(
        id=personality.id,
        name=fields.name,
        icon=fields.icon,
        system_prompt=fields.system_prompt,
        params=fields.params,
    )


async def _snapshot(
    personalities: PersonalityRepository, personality_id: str
) -> PersonalitySnapshot:
    personality = await personalities.get(personality_id)
    if personality is None:
        raise PersonalityNotFoundError
    return _snapshot_of(personality)


def _resolve_model(requested: str | None, fallback: str, settings: Settings) -> str:
    model = requested or fallback or settings.default_model
    if not model:
        raise BadRequestError("Indica un modelo: no hay DEFAULT_MODEL configurado")
    return model


@router.get("")
async def list_conversations(repo: Repo) -> ConversationList:
    return ConversationList(conversations=[ConversationOut.of(c) for c in await repo.list_all()])


@router.post("", status_code=201)
async def create_conversation(
    body: NewConversation,
    repo: Repo,
    personalities: Annotated[PersonalityRepository, Depends(get_personality_repository)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ConversationOut:
    """The personality is fixed here: its prompt and parameters are copied into the conversation."""
    personality = await personalities.get(body.personality_id or DEFAULT_PERSONALITY_ID)
    if personality is None:
        raise PersonalityNotFoundError
    model = _resolve_model(body.model, personality.fields.default_model or "", settings)
    snapshot = _snapshot_of(personality)
    return ConversationOut.of(await repo.create("Nueva conversación", model, snapshot))


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: ConversationId,
    repo: Repo,
    attachments: Attachments,
    feedback: Annotated[FeedbackRepository, Depends(get_feedback_repository)],
) -> ConversationDetail:
    conversation = await _require(repo, conversation_id)
    messages = await repo.messages(conversation_id)
    by_message = _by_message(await attachments.list_for_conversation(conversation_id))
    ratings = await feedback.for_conversation(conversation_id)
    return ConversationDetail(
        **ConversationOut.of(conversation).model_dump(),
        messages=[MessageOut.of(m, by_message.get(m.id), ratings.get(m.id)) for m in messages],
    )


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: ConversationId,
    body: ConversationPatch,
    repo: Repo,
    personalities: Annotated[PersonalityRepository, Depends(get_personality_repository)],
) -> ConversationOut:
    await _require(repo, conversation_id)
    if body.personality_id is not None:
        snapshot = await _snapshot(personalities, body.personality_id)
        if not await repo.set_personality_if_draft(conversation_id, snapshot):
            await _require(repo, conversation_id)  # deleted meanwhile -> 404, not 409
            raise PersonalityLockedError
    updated = await repo.update(conversation_id, title=body.title)
    if updated is None:
        raise ConversationNotFoundError
    return ConversationOut.of(updated)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: ConversationId,
    repo: Repo,
    attachments: Attachments,
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> None:
    # The rows go with the conversation (ON DELETE CASCADE); the files on disk are removed here.
    keys = await attachments.storage_keys(conversation_id)
    if not await repo.delete(conversation_id):
        raise ConversationNotFoundError
    for key in keys:
        try:
            await storage.delete(key)
        except OSError as exc:  # the rest still go; the startup sweep retries leftovers
            logger.warning("Could not delete an attachment file: %s", type(exc).__name__)


@router.post(
    "/{conversation_id}/messages",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def send_message(
    conversation_id: ConversationId,
    body: SendMessage,
    repo: Repo,
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
    osint_sources: Annotated[OsintSourceRepository, Depends(get_osint_source_repository)],
    attachments: Attachments,
    storage: Annotated[FileStorage, Depends(get_file_storage)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    memories: Annotated[MemoryRepository, Depends(get_memory_repository)],
    app_settings: Annotated[AppSettingsRepository, Depends(get_app_settings_repository)],
) -> StreamingResponse:
    """Save the user message, stream the reply (same SSE events as /api/chat) and save it.

    The reply is saved as `done`, `stopped` (client disconnected) or `error`. Failed turns and
    empty replies are not sent back to the model as history.
    """
    conversation = await _require(repo, conversation_id)
    model = _resolve_model(body.model, conversation.model, settings)

    # Attachments must belong to this conversation and not have been sent before.
    requested = list(dict.fromkeys(body.attachment_ids))
    sending: list[Attachment] = []
    for attachment_id in requested:
        attachment = await attachments.get(conversation_id, attachment_id)
        if attachment is None:
            raise AttachmentNotFoundError
        if attachment.message_id is not None:
            raise BadRequestError("Ese fichero ya se envió en otro mensaje")
        sending.append(attachment)

    vision = await llm.supports_vision(model)
    if not vision and any(a.kind == "image" for a in sending):
        raise ModelWithoutVisionError

    previous = await repo.messages(conversation_id)
    is_first_message = not any(m.role == "user" for m in previous)
    snapshot = conversation.personality
    budget, params = context_for(model, snapshot.params, settings)

    # The system prompt is composed on every turn (never stored as a message): the base layer
    # comes from code, so a fix to it also reaches older conversations; the personality layer
    # is the conversation's own snapshot.
    # The OSINT catalog is knowledge, not part of the snapshot: the Auditor always gets the
    # sources that are active right now (ADR-014).
    reference = ""
    if needs_osint_catalog(snapshot.id):
        reference = format_osint_catalog(await osint_sources.list_all(active_only=True))
    # The user's memory (ADR-025) goes to local models; to cloud ones only if the user allowed it.
    provider = settings.provider_for(model)
    remote = provider is not None and not provider.local
    injected: list[Memory] = []
    if not remote or await app_settings.memory_to_remote():
        injected = await memories.in_use(datetime.now(UTC))
    system_prompt = compose_system_prompt(
        snapshot.system_prompt, reference, format_memory_block(injected)
    )

    # File contents go inside the user's message as delimited DATA, never in the system prompt.
    by_message = _by_message(await attachments.list_for_conversation(conversation_id))
    earlier = [m for m in previous if m.status != "error" and m.content.strip()]
    # Images travel as images, only to a vision model, and only the newest few (each costs
    # hundreds of tokens and GPU time on every turn); older ones keep just their name.
    images = [
        a
        for m in earlier
        if m.role == "user"
        for a in by_message.get(m.id, [])
        if a.kind == "image"
    ] + [a for a in sending if a.kind == "image"]
    chosen = {a.id for a in images[-MAX_IMAGES_PER_REQUEST:]} if vision else set()

    async def images_of(files: list[Attachment]) -> tuple[ImageData, ...]:
        loaded: list[ImageData] = []
        for a in files:
            if a.id not in chosen:
                continue
            try:
                loaded.append(ImageData(mime=a.mime, data=await storage.read(a.storage_key)))
            except (FileNotFoundError, ValueError):
                logger.warning("Image attachment file missing")
        return tuple(loaded)

    turns: list[Turn] = []
    for m in earlier:
        files = by_message.get(m.id, []) if m.role == "user" else []
        turns.append(Turn(role=m.role, text=m.content, files=files, images=await images_of(files)))
    current = Turn(role="user", text=body.content, files=sending, images=await images_of(sending))
    # Shaped to the model's window BEFORE anything is stored: a message that can't fit is
    # refused (400 CONTEXT_TOO_LONG) instead of failing at the model.
    fitted = fit_history(system_prompt, turns, current, budget)
    if fitted.dropped_turns or fitted.dropped_images or fitted.omitted_files:
        logger.info(
            "History fitted to %d tokens: %d turns dropped, %d images and %d files left out",
            budget,
            fitted.dropped_turns,
            fitted.dropped_images,
            fitted.omitted_files,
        )

    user_message = await repo.add_message(conversation_id, "user", body.content, "done")
    # The checks above and this update are separate steps: a concurrent send may have taken a
    # file in between. Only the update decides; on a shortfall the turn is undone.
    linked = await attachments.attach_to_message(conversation_id, requested, user_message.id)
    if linked != len(requested):
        await attachments.release(user_message.id)
        await repo.delete_message(conversation_id, user_message.id)
        raise BadRequestError("Ese fichero ya se envió en otro mensaje")
    # The snapshot was read before the slow steps above; a draft's personality may have changed
    # in between (ADR-022). From here on the user message exists, so it can't change any more:
    # if it did, undo and let the client send again with what it now shows.
    current = await repo.get(conversation_id)
    if current is None or current.personality != snapshot:
        await attachments.release(user_message.id)
        await repo.delete_message(conversation_id, user_message.id)
        raise PersonalityLockedError(
            "La personalidad de la conversación ha cambiado; vuelve a enviar el mensaje"
        )

    provider = settings.provider_for(model)
    generation = Generation(
        model=model,
        provider=provider.name if provider else "ollama",
        base_prompt_version=BASE_PROMPT_VERSION,
    )

    async def save_reply(content: str, status: MessageStatus) -> int:
        saved = await repo.add_message(conversation_id, "assistant", content, status, generation)
        return saved.id

    async def undo_turn() -> None:
        # The model failed before answering (rate limit, unreachable...): the turn didn't
        # happen. The client puts the text back in the composer and the files are pending again.
        await attachments.release(user_message.id)
        await repo.delete_message(conversation_id, user_message.id)

    response = await stream_reply(
        llm,
        model,
        fitted.messages,
        on_finish=save_reply,
        params=params,
        on_early_error=undo_turn,
    )
    # Only once the model has started answering does the conversation take its model and title.
    await repo.update(
        conversation_id,
        model=model,
        title=title_from_message(body.content) if is_first_message else None,
    )
    return response
