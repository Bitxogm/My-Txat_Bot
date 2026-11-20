from collections.abc import AsyncIterator, Sequence

import pytest

from app.adapters.routing import RoutingLLMProvider
from app.core.errors import ModelUnavailableError
from app.domain.chat import ChatMessage, ModelInfo


class Stub:
    def __init__(self, name: str, models: list[str], fail: bool = False) -> None:
        self.name = name
        self._models = models
        self._fail = fail
        self.calls: list[str] = []

    async def is_available(self) -> bool:
        return not self._fail

    async def list_models(self) -> list[ModelInfo]:
        if self._fail:
            raise ModelUnavailableError()
        return [ModelInfo(name=m, size_bytes=0, remote=self.name != "local") for m in self._models]

    async def stream_chat(self, model: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.calls.append(model)
        yield self.name


MSG = [ChatMessage(role="user", content="x")]


async def drain(it: AsyncIterator[str]) -> list[str]:
    return [c async for c in it]


async def test_merges_models_with_remote_prefix() -> None:
    router = RoutingLLMProvider(
        Stub("local", ["qwen3.5:9b"]), [Stub("groq", ["openai/gpt-oss-120b"])]
    )

    models = await router.list_models()

    assert [(m.name, m.remote) for m in models] == [
        ("qwen3.5:9b", False),
        ("groq/openai/gpt-oss-120b", True),
    ]


async def test_routes_by_prefix() -> None:
    local, groq = Stub("local", []), Stub("groq", [])
    router = RoutingLLMProvider(local, [groq])

    assert await drain(router.stream_chat("groq/openai/gpt-oss-120b", MSG)) == ["groq"]
    assert await drain(router.stream_chat("qwen3.5:9b", MSG)) == ["local"]
    assert await drain(router.stream_chat("hf.co/user/model", MSG)) == ["local"]
    assert groq.calls == ["openai/gpt-oss-120b"]


async def test_one_failing_provider_does_not_hide_the_other() -> None:
    router = RoutingLLMProvider(Stub("local", ["q"], fail=True), [Stub("groq", ["g"])])

    assert [m.name for m in await router.list_models()] == ["groq/g"]


async def test_all_failing_raises() -> None:
    router = RoutingLLMProvider(Stub("local", [], fail=True), [Stub("groq", [], fail=True)])

    with pytest.raises(ModelUnavailableError):
        await router.list_models()


async def test_health_reflects_local_only() -> None:
    router = RoutingLLMProvider(Stub("local", [], fail=True), [Stub("groq", [])])

    assert await router.is_available() is False
