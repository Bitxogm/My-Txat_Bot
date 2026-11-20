import json
from collections.abc import Callable

import httpx
from fastapi import FastAPI

from app.api.dependencies import get_llm_provider
from app.core.errors import ModelNotFoundError, ModelUnavailableError
from app.main import create_app
from tests.conftest import FakeLLMProvider, make_settings

USER_MESSAGE = {"role": "user", "content": "hola"}


def parse_sse(text: str) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def test_streams_tokens_then_done(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    response = await client.post("/api/chat", json={"model": "m", "messages": [USER_MESSAGE]})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert parse_sse(response.text) == [
        ("token", {"content": "Hola"}),
        ("token", {"content": " mundo"}),
        ("done", {"model": "m"}),
    ]
    model, messages = fake_llm.calls[0]
    assert model == "m"
    assert messages[0].role == "user"
    assert messages[0].content == "hola"


async def test_uses_default_model(
    fake_llm: FakeLLMProvider, make_client: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    app = create_app(make_settings(default_model="default:7b"))
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm

    async with make_client(app) as c:
        response = await c.post("/api/chat", json={"messages": [USER_MESSAGE]})

    assert response.status_code == 200
    assert fake_llm.calls[0][0] == "default:7b"


async def test_requires_model_without_default(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/chat", json={"messages": [USER_MESSAGE]})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"


async def test_unknown_model_is_a_json_error(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.fail_before = ModelNotFoundError()

    response = await client.post("/api/chat", json={"model": "nope", "messages": [USER_MESSAGE]})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"


async def test_error_mid_stream_is_an_sse_event(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.fail_after = ModelUnavailableError()

    response = await client.post(
        "/api/chat",
        json={"model": "m", "messages": [USER_MESSAGE]},
        headers={"X-Request-ID": "req-1"},
    )

    events = parse_sse(response.text)
    assert response.status_code == 200
    assert events[:2] == [("token", {"content": "Hola"}), ("token", {"content": " mundo"})]
    assert events[2][0] == "error"
    assert events[2][1]["code"] == "MODEL_UNAVAILABLE"
    assert events[2][1]["request_id"] == "req-1"


async def test_rejects_invalid_role(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/chat", json={"model": "m", "messages": [{"role": "tool", "content": "x"}]}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_rejects_empty_messages(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/chat", json={"model": "m", "messages": []})

    assert response.status_code == 422
