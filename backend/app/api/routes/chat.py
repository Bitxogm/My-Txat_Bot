from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_app_settings, get_llm_provider
from app.api.streaming import stream_reply
from app.core.config import Settings
from app.core.errors import BadRequestError
from app.domain.chat import ChatMessage
from app.domain.prompts import compose_system_prompt
from app.ports.llm import LLMProvider

router = APIRouter(tags=["chat"])

MAX_MESSAGES = 200
MAX_CONTENT_CHARS = 100_000


class ChatMessageIn(BaseModel):
    # No "system": the client must not be able to add instructions after the base layer.
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)


class ChatRequest(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=200)
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=MAX_MESSAGES)


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def chat(
    body: ChatRequest,
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> StreamingResponse:
    """Stateless chat: the client sends the whole history. See stream_reply for the events.

    The base layer is always prepended, so this path has the same limits as conversations.
    """
    model = body.model or settings.default_model
    if not model:
        raise BadRequestError("Indica un modelo: no hay DEFAULT_MODEL configurado")

    messages = [ChatMessage(role="system", content=compose_system_prompt(""))]
    messages += [ChatMessage(role=m.role, content=m.content) for m in body.messages]
    return await stream_reply(llm, model, messages)
