from collections.abc import AsyncIterator, Callable, Sequence

import httpx
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI

from app.adapters.sqlite.conversations import SqliteConversationRepository
from app.adapters.sqlite.database import connect
from app.api.dependencies import get_llm_provider
from app.core.config import Settings
from app.core.errors import AppError
from app.domain.chat import ChatMessage, ModelInfo
from app.domain.personality import GenerationParams
from app.main import create_app


class FakeLLMProvider:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.models: list[ModelInfo] = [ModelInfo(name="fake:7b", size_bytes=1)]
        self.chunks: list[str] = ["Hola", " mundo"]
        self.fail_before: AppError | None = None
        self.fail_after: AppError | None = None
        self.calls: list[tuple[str, list[ChatMessage]]] = []
        self.params: list[GenerationParams | None] = []

    async def is_available(self) -> bool:
        return self.available

    async def list_models(self) -> list[ModelInfo]:
        if self.fail_before:
            raise self.fail_before
        return self.models

    async def stream_chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        params: GenerationParams | None = None,
    ) -> AsyncIterator[str]:
        self.calls.append((model, list(messages)))
        self.params.append(params)
        if self.fail_before:
            raise self.fail_before
        for chunk in self.chunks:
            yield chunk
        if self.fail_after:
            raise self.fail_after


TEST_USERNAME = "void"
TEST_PASSWORD = "correct horse battery staple"
# Cheap parameters keep the suite fast; verification reads them from the hash itself.
TEST_PASSWORD_HASH = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(TEST_PASSWORD)
TEST_SESSION_SECRET = "s" * 48


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "auth_username": TEST_USERNAME,
        "auth_password_hash": TEST_PASSWORD_HASH,
        "session_secret": TEST_SESSION_SECRET,
    }
    values.update(overrides)
    return Settings(app_env="test", _env_file=None, **values)  # type: ignore[call-arg, arg-type]


async def log_in(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    assert response.status_code == 204, response.text


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
async def repo() -> AsyncIterator[SqliteConversationRepository]:
    db = await connect(":memory:")
    yield SqliteConversationRepository(db)
    await db.close()


@pytest.fixture
def app(fake_llm: FakeLLMProvider, repo: SqliteConversationRepository) -> FastAPI:
    # ASGITransport doesn't run the lifespan, so wire what it would have created.
    application = create_app(make_settings())
    application.dependency_overrides[get_llm_provider] = lambda: fake_llm
    application.state.conversations = repo
    return application


@pytest.fixture
def make_client() -> Callable[[FastAPI], httpx.AsyncClient]:
    def _make(application: FastAPI) -> httpx.AsyncClient:
        transport = httpx.ASGITransport(app=application)
        return httpx.AsyncClient(transport=transport, base_url="http://testserver")

    return _make


@pytest.fixture
async def anon_client(
    app: FastAPI, make_client: Callable[[FastAPI], httpx.AsyncClient]
) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(app) as c:
        yield c


@pytest.fixture
async def client(anon_client: httpx.AsyncClient) -> httpx.AsyncClient:
    await log_in(anon_client)
    return anon_client
