import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import anyio
from fastapi.responses import StreamingResponse

from app.core.errors import AppError
from app.core.request_id import get_request_id
from app.domain.chat import ChatMessage
from app.domain.conversation import MessageStatus
from app.domain.personality import GenerationParams
from app.ports.llm import LLMProvider

logger = logging.getLogger(__name__)

# Called once with the full reply and how it ended (done / stopped by the client / error).
OnFinish = Callable[[str, MessageStatus], Awaitable[None]]


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error_event(exc: AppError | None = None) -> str:
    return sse(
        "error",
        {
            "code": exc.code if exc else AppError.code,
            "message": exc.message if exc else AppError.message,
            "request_id": get_request_id(),
        },
    )


async def stream_reply(
    llm: LLMProvider,
    model: str,
    messages: Sequence[ChatMessage],
    on_finish: OnFinish | None = None,
    params: GenerationParams | None = None,
) -> StreamingResponse:
    """Stream a model reply as SSE: `token`* then `done`, or `error`.

    Errors before the first token raise, so the route answers with the usual JSON error and
    HTTP status; errors after streaming starts arrive as an `error` event.
    """
    chunks = aiter(llm.stream_chat(model, messages, params))
    # Pull the first chunk here so early failures become a normal HTTP error response.
    try:
        first = await anext(chunks, None)
    except AppError:
        if on_finish:
            await on_finish("", "error")
        raise

    async def events() -> AsyncIterator[str]:
        content = first or ""
        status: MessageStatus = "stopped"  # unless the loop finishes or fails
        finished = False
        try:
            if first is not None:
                yield sse("token", {"content": first})
            async for chunk in chunks:
                content += chunk
                yield sse("token", {"content": chunk})
            status = "done"
            if on_finish:
                await on_finish(content, status)
            finished = True
            yield sse("done", {"model": model})
        except AppError as exc:
            status = "error"
            logger.warning("Chat stream failed: %s", exc.code)
            yield _error_event(exc)
        except Exception:
            status = "error"
            logger.exception("Unhandled error while streaming chat")
            yield _error_event()
        finally:
            # On client disconnect, close the upstream stream so Ollama stops generating.
            aclose = getattr(chunks, "aclose", None)
            if aclose is not None:
                await aclose()
            if on_finish and not finished:
                # Shielded: on disconnect this runs inside a cancelled scope.
                with anyio.CancelScope(shield=True):
                    await on_finish(content, status)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
