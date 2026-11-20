import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_app_settings, get_llm_provider
from app.core.config import Settings
from app.core.errors import AppError, BadRequestError
from app.core.request_id import get_request_id
from app.domain.chat import ChatMessage, Role
from app.ports.llm import LLMProvider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

MAX_MESSAGES = 200
MAX_CONTENT_CHARS = 100_000


class ChatMessageIn(BaseModel):
    role: Role
    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)


class ChatRequest(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=200)
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=MAX_MESSAGES)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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
    """Stream the reply as Server-Sent Events: `token`* then `done`, or `error`.

    Errors found before the first token (unknown model, Ollama down) return the usual JSON
    error with its HTTP status; errors after streaming starts arrive as an `error` event.
    """
    model = body.model or settings.default_model
    if not model:
        raise BadRequestError("Indica un modelo: no hay DEFAULT_MODEL configurado")

    messages = [ChatMessage(role=m.role, content=m.content) for m in body.messages]
    chunks = aiter(llm.stream_chat(model, messages))
    # Pull the first chunk here so early failures become a normal HTTP error response.
    first = await anext(chunks, None)

    async def events() -> AsyncIterator[str]:
        try:
            if first is not None:
                yield _sse("token", {"content": first})
            async for chunk in chunks:
                yield _sse("token", {"content": chunk})
            yield _sse("done", {"model": model})
        except AppError as exc:
            logger.warning("Chat stream failed: %s", exc.code)
            yield _sse(
                "error",
                {"code": exc.code, "message": exc.message, "request_id": get_request_id()},
            )
        except Exception:
            logger.exception("Unhandled error while streaming chat")
            yield _sse(
                "error",
                {
                    "code": AppError.code,
                    "message": AppError.message,
                    "request_id": get_request_id(),
                },
            )
        finally:
            # On client disconnect, close the upstream stream so Ollama stops generating.
            aclose = getattr(chunks, "aclose", None)
            if aclose is not None:
                await aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
