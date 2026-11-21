import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.dependencies import (
    get_app_settings,
    get_attachment_repository,
    get_conversation_repository,
    get_file_storage,
    get_llm_provider,
    get_osint_source_repository,
    get_personality_repository,
)
from app.api.routes.chat import MAX_CONTENT_CHARS
from app.api.routes.personalities import PERSONALITY_ID_PATTERN
from app.api.streaming import stream_reply
from app.core.config import Settings
from app.core.errors import (
    AttachmentNotFoundError,
    BadRequestError,
    ConversationNotFoundError,
    ModelWithoutVisionError,
    PersonalityNotFoundError,
)
from app.domain.attachment import (
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_IMAGES_PER_REQUEST,
    Attachment,
    format_attachments_for_model,
)
from app.domain.chat import ChatMessage, ImageData, Role
from app.domain.conversation import (
    TITLE_MAX_CHARS,
    Conversation,
    MessageStatus,
    PersonalitySnapshot,
    StoredMessage,
    title_from_message,
)
from app.domain.osint import format_osint_catalog, needs_osint_catalog
from app.domain.personality import DEFAULT_PERSONALITY_ID
from app.domain.prompts import compose_system_prompt
from app.ports.attachments import AttachmentRepository
from app.ports.conversations import ConversationRepository
from app.ports.file_storage import FileStorage
from app.ports.llm import LLMProvider
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


class MessageOut(BaseModel):
    id: int
    role: Role
    content: str
    status: MessageStatus
    created_at: datetime
    attachments: list[MessageAttachment] = []

    @classmethod
    def of(cls, m: StoredMessage, attachments: list[Attachment] | None = None) -> "MessageOut":
        return cls(
            id=m.id,
            role=m.role,
            content=m.content,
            status=m.status,
            created_at=m.created_at,
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
    # Only the title is editable; the personality snapshot can't be changed (ADR-013).
    model_config = ConfigDict(extra="forbid")

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_CHARS)
    ]


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
    fields = personality.fields
    model = _resolve_model(body.model, fields.default_model or "", settings)
    snapshot = PersonalitySnapshot(
        id=personality.id,
        name=fields.name,
        icon=fields.icon,
        system_prompt=fields.system_prompt,
        params=fields.params,
    )
    return ConversationOut.of(await repo.create("Nueva conversación", model, snapshot))


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: ConversationId, repo: Repo, attachments: Attachments
) -> ConversationDetail:
    conversation = await _require(repo, conversation_id)
    messages = await repo.messages(conversation_id)
    by_message = _by_message(await attachments.list_for_conversation(conversation_id))
    return ConversationDetail(
        **ConversationOut.of(conversation).model_dump(),
        messages=[MessageOut.of(m, by_message.get(m.id)) for m in messages],
    )


@router.patch("/{conversation_id}")
async def rename_conversation(
    conversation_id: ConversationId, body: ConversationPatch, repo: Repo
) -> ConversationOut:
    await _require(repo, conversation_id)
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
    user_message = await repo.add_message(conversation_id, "user", body.content, "done")
    # The checks above and this update are separate steps: a concurrent send may have taken a
    # file in between. Only the update decides; on a shortfall the turn is undone.
    linked = await attachments.attach_to_message(conversation_id, requested, user_message.id)
    if linked != len(requested):
        await attachments.release(user_message.id)
        await repo.delete_message(conversation_id, user_message.id)
        raise BadRequestError("Ese fichero ya se envió en otro mensaje")
    await repo.update(
        conversation_id,
        model=model,
        title=title_from_message(body.content) if is_first_message else None,
    )

    snapshot = conversation.personality
    # The system prompt is composed on every turn (never stored as a message): the base layer
    # comes from code, so a fix to it also reaches older conversations; the personality layer
    # is the conversation's own snapshot.
    # The OSINT catalog is knowledge, not part of the snapshot: the Auditor always gets the
    # sources that are active right now (ADR-014).
    reference = ""
    if needs_osint_catalog(snapshot.id):
        reference = format_osint_catalog(await osint_sources.list_all(active_only=True))
    system_prompt = compose_system_prompt(snapshot.system_prompt, reference)
    history = [ChatMessage(role="system", content=system_prompt)]
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

    for m in earlier:
        if m.role == "user":
            files = by_message.get(m.id, [])
            history.append(
                ChatMessage(
                    role="user",
                    content=format_attachments_for_model(files, m.content),
                    images=await images_of(files),
                )
            )
        else:
            history.append(ChatMessage(role=m.role, content=m.content))
    history.append(
        ChatMessage(
            role="user",
            content=format_attachments_for_model(sending, body.content),
            images=await images_of(sending),
        )
    )

    async def save_reply(content: str, status: MessageStatus) -> None:
        await repo.add_message(conversation_id, "assistant", content, status)

    return await stream_reply(llm, model, history, on_finish=save_reply, params=snapshot.params)
