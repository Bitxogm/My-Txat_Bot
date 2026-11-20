import json

import httpx
import pytest

from app.adapters.ollama.provider import OllamaProvider
from app.core.errors import EmptyReplyError, ModelNotFoundError, ModelUnavailableError
from app.domain.chat import ChatMessage, ModelInfo


def provider_with(handler: httpx.MockTransport) -> OllamaProvider:
    return OllamaProvider(httpx.AsyncClient(transport=handler, base_url="http://ollama.test"))


async def test_available_when_version_answers() -> None:
    provider = provider_with(
        httpx.MockTransport(lambda _: httpx.Response(200, json={"version": "0.0.0"}))
    )

    assert await provider.is_available() is True


async def test_unavailable_on_error_status() -> None:
    provider = provider_with(httpx.MockTransport(lambda _: httpx.Response(500)))

    assert await provider.is_available() is False


async def test_unavailable_when_unreachable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    provider = provider_with(httpx.MockTransport(refuse))

    assert await provider.is_available() is False


def ndjson(*objs: object) -> bytes:
    return b"".join(json.dumps(o).encode() + b"\n" for o in objs)


async def collect(provider: OllamaProvider) -> list[str]:
    return [c async for c in provider.stream_chat("m", [ChatMessage(role="user", content="hola")])]


async def test_list_models_maps_tags() -> None:
    tags = {
        "models": [
            {
                "name": "llama3.1:8b",
                "size": 4920753328,
                "details": {
                    "family": "llama",
                    "parameter_size": "8.0B",
                    "quantization_level": "Q4_K_M",
                },
            }
        ]
    }
    provider = provider_with(httpx.MockTransport(lambda _: httpx.Response(200, json=tags)))

    assert await provider.list_models() == [
        ModelInfo(
            name="llama3.1:8b",
            size_bytes=4920753328,
            family="llama",
            parameter_size="8.0B",
            quantization="Q4_K_M",
        )
    ]


async def test_list_models_unreachable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ModelUnavailableError):
        await provider_with(httpx.MockTransport(refuse)).list_models()


async def test_stream_chat_yields_content_until_done() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        body = ndjson(
            {"message": {"role": "assistant", "content": "Ho"}, "done": False},
            {"message": {"role": "assistant", "content": "la"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True},
        )
        return httpx.Response(200, content=body)

    assert await collect(provider_with(httpx.MockTransport(handler))) == ["Ho", "la"]
    assert seen[0] == {
        "model": "m",
        "messages": [{"role": "user", "content": "hola"}],
        "stream": True,
        "think": False,
    }


async def test_stream_chat_unknown_model() -> None:
    provider = provider_with(
        httpx.MockTransport(lambda _: httpx.Response(404, json={"error": "model not found"}))
    )

    with pytest.raises(ModelNotFoundError):
        await collect(provider)


async def test_stream_chat_error_line() -> None:
    body = ndjson({"message": {"content": "a"}, "done": False}, {"error": "out of memory"})
    provider = provider_with(httpx.MockTransport(lambda _: httpx.Response(200, content=body)))

    with pytest.raises(ModelUnavailableError):
        await collect(provider)


async def test_stream_chat_unreachable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ModelUnavailableError):
        await collect(provider_with(httpx.MockTransport(refuse)))


async def test_think_can_be_enabled() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=ndjson({"message": {"content": "a"}, "done": True}))

    provider = OllamaProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://o.test"),
        think=True,
    )
    await collect(provider)

    assert seen[0]["think"] is True


async def test_reply_with_only_thinking_is_an_empty_reply() -> None:
    body = ndjson(
        {"message": {"content": "", "thinking": "hmm"}, "done": False},
        {"message": {"content": ""}, "done": True, "done_reason": "stop"},
    )
    provider = provider_with(httpx.MockTransport(lambda _: httpx.Response(200, content=body)))

    with pytest.raises(EmptyReplyError) as exc:
        await collect(provider)
    assert exc.value.message == "El modelo no devolvió ninguna respuesta"


async def test_length_limit_without_text_explains_why() -> None:
    body = ndjson(
        {"message": {"content": "", "thinking": "..."}, "done": False},
        {"message": {"content": ""}, "done": True, "done_reason": "length"},
    )
    provider = provider_with(httpx.MockTransport(lambda _: httpx.Response(200, content=body)))

    with pytest.raises(EmptyReplyError) as exc:
        await collect(provider)
    assert "límite de longitud" in exc.value.message
    assert exc.value.status_code == 502


async def test_truncated_reply_with_text_is_kept() -> None:
    body = ndjson(
        {"message": {"content": "parcial"}, "done": False},
        {"message": {"content": ""}, "done": True, "done_reason": "length"},
    )
    provider = provider_with(httpx.MockTransport(lambda _: httpx.Response(200, content=body)))

    assert await collect(provider) == ["parcial"]
