from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from fastapi import FastAPI

from app.api.dependencies import get_llm_provider
from app.core.config import Settings
from app.main import create_app


class FakeLLMProvider:
    def __init__(self, available: bool = True) -> None:
        self.available = available

    async def is_available(self) -> bool:
        return self.available


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
def app(fake_llm: FakeLLMProvider) -> FastAPI:
    application = create_app(Settings(app_env="test", _env_file=None))  # type: ignore[call-arg]
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
