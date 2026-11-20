from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from app.api.dependencies import (
    get_app_settings,
    get_conversation_repository,
    get_llm_provider,
    get_personality_repository,
)
from app.api.routes.chat import MAX_CONTENT_CHARS
from app.api.routes.personalities import PERSONALITY_ID_PATTERN
from app.api.streaming import stream_reply
from app.core.config import Settings
from app.core.errors import (
    BadRequestError,
    ConversationNotFoundError,
    PersonalityNotFoundError,
)
from app.domain.chat import ChatMessage, Role
from app.domain.conversation import (
    TITLE_MAX_CHARS,
    Conversation,
    MessageStatus,
    PersonalitySnapshot,
    StoredMessage,
    title_from_message,
)
from app.domain.personality import DEFAULT_PERSONALITY_ID
from app.domain.prompts import compose_system_prompt
from app.ports.conversations import ConversationRepository
from app.ports.llm import LLMProvider
from app.ports.personalities import PersonalityRepository

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


class MessageOut(BaseModel):
    id: int
    role: Role
    content: str
    status: MessageStatus
    created_at: datetime

    @classmethod
    def of(cls, m: StoredMessage) -> "MessageOut":
        return cls(
            id=m.id, role=m.role, content=m.content, status=m.status, created_at=m.created_at
        )


class ConversationList(BaseModel):
    conversations: list[ConversationOut]


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationPatch(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_CHARS)
    ]


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    model: str | None = Field(default=None, min_length=1, max_length=200)


class NewConversation(BaseModel):
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
async def get_conversation(conversation_id: ConversationId, repo: Repo) -> ConversationDetail:
    conversation = await _require(repo, conversation_id)
    messages = await repo.messages(conversation_id)
    return ConversationDetail(
        **ConversationOut.of(conversation).model_dump(),
        messages=[MessageOut.of(m) for m in messages],
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
async def delete_conversation(conversation_id: ConversationId, repo: Repo) -> None:
    if not await repo.delete(conversation_id):
        raise ConversationNotFoundError


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
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> StreamingResponse:
    """Save the user message, stream the reply (same SSE events as /api/chat) and save it.

    The reply is saved as `done`, `stopped` (client disconnected) or `error`. Failed turns and
    empty replies are not sent back to the model as history.
    """
    conversation = await _require(repo, conversation_id)
    model = _resolve_model(body.model, conversation.model, settings)

    previous = await repo.messages(conversation_id)
    is_first_message = not any(m.role == "user" for m in previous)
    await repo.add_message(conversation_id, "user", body.content, "done")
    await repo.update(
        conversation_id,
        model=model,
        title=title_from_message(body.content) if is_first_message else None,
    )

    snapshot = conversation.personality
    # The system prompt is composed on every turn (never stored as a message): the base layer
    # comes from code, so a fix to it also reaches older conversations; the personality layer
    # is the conversation's own snapshot.
    history = [ChatMessage(role="system", content=compose_system_prompt(snapshot.system_prompt))]
    history += [
        ChatMessage(role=m.role, content=m.content)
        for m in previous
        if m.status != "error" and m.content.strip()
    ]
    history.append(ChatMessage(role="user", content=body.content))

    async def save_reply(content: str, status: MessageStatus) -> None:
        await repo.add_message(conversation_id, "assistant", content, status)

    return await stream_reply(llm, model, history, on_finish=save_reply, params=snapshot.params)
