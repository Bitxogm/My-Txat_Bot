import httpx

from app.adapters.ollama.provider import OllamaProvider


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
