import json

import httpx
import pytest

from app.adapters.openai_compat.provider import (
    OpenAICompatibleProvider,
    build_openai_compatible_client,
)
from app.core.errors import (
    EmptyReplyError,
    ModelNotFoundError,
    ModelRateLimitedError,
    ModelUnavailableError,
)
from app.domain.chat import ChatMessage

MODELS = {
    "data": [
        {"id": "openai/gpt-oss-120b"},
        {"id": "llama-3.3-70b-versatile"},
        {"id": "whisper-large-v3"},
        {"id": "meta-llama/llama-guard-4-12b"},
    ]
}


def provider(
    handler: httpx.MockTransport, allowed: tuple[str, ...] = ()
) -> OpenAICompatibleProvider:
    client = httpx.AsyncClient(transport=handler, base_url="https://cloud.test/v1")
    return OpenAICompatibleProvider(client, "groq", allowed_models=allowed)


def sse(*chunks: object) -> bytes:
    lines = [f"data: {json.dumps(c)}\n\n" for c in chunks] + ["data: [DONE]\n\n"]
    return "".join(lines).encode()


def delta(text: str, finish: str | None = None) -> dict[str, object]:
    return {"choices": [{"delta": {"content": text}, "finish_reason": finish}]}


async def collect(p: OpenAICompatibleProvider) -> list[str]:
    return [c async for c in p.stream_chat("m", [ChatMessage(role="user", content="hola")])]


async def test_lists_only_chat_models_marked_remote() -> None:
    p = provider(httpx.MockTransport(lambda _: httpx.Response(200, json=MODELS)))

    models = await p.list_models()

    assert [m.name for m in models] == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]
    assert all(m.remote for m in models)


async def test_allowlist_wins() -> None:
    p = provider(
        httpx.MockTransport(lambda _: httpx.Response(200, json=MODELS)),
        allowed=("openai/gpt-oss-120b",),
    )

    assert [m.name for m in await p.list_models()] == ["openai/gpt-oss-120b"]


async def test_streams_content_and_sends_openai_payload() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = sse(
            {"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]},
            delta("Ho"),
            delta("la"),
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        )
        return httpx.Response(200, content=body)

    assert await collect(provider(httpx.MockTransport(handler))) == ["Ho", "la"]
    assert seen[0].url.path == "/v1/chat/completions"
    assert json.loads(seen[0].content) == {
        "model": "m",
        "messages": [{"role": "user", "content": "hola"}],
        "stream": True,
    }


def test_client_sends_bearer_key() -> None:
    client = build_openai_compatible_client("https://cloud.test/v1/", "k-123", 5)

    assert client.headers["Authorization"] == "Bearer k-123"
    assert str(client.base_url) == "https://cloud.test/v1/"


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, ModelUnavailableError),
        (403, ModelUnavailableError),
        (404, ModelNotFoundError),
        (429, ModelRateLimitedError),
        (500, ModelUnavailableError),
    ],
)
async def test_maps_http_errors(status: int, error: type[Exception]) -> None:
    p = provider(httpx.MockTransport(lambda _: httpx.Response(status, json={"error": {}})))

    with pytest.raises(error):
        await collect(p)


async def test_rate_limit_passes_retry_after() -> None:
    p = provider(httpx.MockTransport(lambda _: httpx.Response(429, headers={"retry-after": "7"})))

    with pytest.raises(ModelRateLimitedError) as exc:
        await collect(p)
    assert exc.value.headers == {"Retry-After": "7"}


async def test_error_in_stream() -> None:
    body = sse(delta("a"), {"error": {"message": "boom"}})
    p = provider(httpx.MockTransport(lambda _: httpx.Response(200, content=body)))

    with pytest.raises(ModelUnavailableError):
        await collect(p)


async def test_empty_reply() -> None:
    body = sse({"choices": [{"delta": {}, "finish_reason": "stop"}]})
    p = provider(httpx.MockTransport(lambda _: httpx.Response(200, content=body)))

    with pytest.raises(EmptyReplyError):
        await collect(p)


async def test_unreachable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ModelUnavailableError):
        await collect(provider(httpx.MockTransport(refuse)))
