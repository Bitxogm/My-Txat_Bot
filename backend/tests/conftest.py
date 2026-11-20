from collections.abc import AsyncIterator, Callable, Sequence

import httpx
import pytest
from fastapi import FastAPI

from app.api.dependencies import get_llm_provider
from app.core.config import Settings
from app.core.errors import AppError
from app.domain.chat import ChatMessage, ModelInfo
from app.main import create_app


class FakeLLMProvider:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.models: list[ModelInfo] = [ModelInfo(name="fake:7b", size_bytes=1)]
        self.chunks: list[str] = ["Hola", " mundo"]
        self.fail_before: AppError | None = None
        self.fail_after: AppError | None = None
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    async def is_available(self) -> bool:
        return self.available

    async def list_models(self) -> list[ModelInfo]:
        if self.fail_before:
            raise self.fail_before
        return self.models

    async def stream_chat(self, model: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.calls.append((model, list(messages)))
        if self.fail_before:
            raise self.fail_before
        for chunk in self.chunks:
            yield chunk
        if self.fail_after:
            raise self.fail_after


def make_settings(**overrides: object) -> Settings:
    return Settings(app_env="test", _env_file=None, **overrides)  # type: ignore[call-arg, arg-type]


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
def app(fake_llm: FakeLLMProvider) -> FastAPI:
    application = create_app(make_settings())
    application.dependency_overrides[get_llm_provider] = lambda: fake_llm
    return application


@pytest.fixture
def make_client() -> Callable[[FastAPI], httpx.AsyncClient]:
    def _make(application: FastAPI) -> httpx.AsyncClient:
        transport = httpx.ASGITransport(app=application)
        return httpx.AsyncClient(transport=transport, base_url="http://testserver")

    return _make


@pytest.fixture
async def client(
    app: FastAPI, make_client: Callable[[FastAPI], httpx.AsyncClient]
) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(app) as c:
        yield c
