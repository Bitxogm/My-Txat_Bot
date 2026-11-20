from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from app.api.dependencies import (
    get_app_settings,
    get_conversation_repository,
    get_llm_provider,
)
from app.api.routes.chat import MAX_CONTENT_CHARS
from app.api.streaming import stream_reply
from app.core.config import Settings
from app.core.errors import BadRequestError, ConversationNotFoundError
from app.domain.chat import ChatMessage, Role
from app.domain.conversation import (
    TITLE_MAX_CHARS,
    Conversation,
    MessageStatus,
    StoredMessage,
    title_from_message,
)
from app.ports.conversations import ConversationRepository
from app.ports.llm import LLMProvider

router = APIRouter(prefix="/conversations", tags=["conversations"])

ConversationId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
Repo = Annotated[ConversationRepository, Depends(get_conversation_repository)]


class ConversationOut(BaseModel):
    id: str
    title: str
    model: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, c: Conversation) -> "ConversationOut":
        return cls(
            id=c.id, title=c.title, model=c.model, created_at=c.created_at, updated_at=c.updated_at
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
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ConversationOut:
    model = _resolve_model(body.model, "", settings)
    return ConversationOut.of(await repo.create("Nueva conversación", model))


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

    history = [
        ChatMessage(role=m.role, content=m.content)
        for m in previous
        if m.status != "error" and m.content.strip()
    ]
    history.append(ChatMessage(role="user", content=body.content))

    async def save_reply(content: str, status: MessageStatus) -> None:
        await repo.add_message(conversation_id, "assistant", content, status)

    return await stream_reply(llm, model, history, on_finish=save_reply)
