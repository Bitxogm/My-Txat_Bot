import json

import httpx
import pytest

from app.adapters.sqlite.conversations import SqliteConversationRepository
from app.api.streaming import stream_reply
from app.core.errors import EmptyReplyError, ModelNotFoundError, ModelUnavailableError
from app.domain.chat import ChatMessage
from tests.conftest import FakeLLMProvider


def parse_sse(text: str) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def create(client: httpx.AsyncClient, model: str = "m") -> str:
    response = await client.post("/api/conversations", json={"model": model})
    assert response.status_code == 201
    return str(response.json()["id"])


async def send(client: httpx.AsyncClient, conversation_id: str, content: str) -> httpx.Response:
    return await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": content}
    )


async def test_requires_a_session(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.get("/api/conversations")).status_code == 401


async def test_create_and_list(client: httpx.AsyncClient) -> None:
    conversation_id = await create(client)

    body = (await client.get("/api/conversations")).json()

    assert [c["id"] for c in body["conversations"]] == [conversation_id]
    assert body["conversations"][0]["title"] == "Nueva conversación"
    assert body["conversations"][0]["model"] == "m"


async def test_create_needs_a_model_or_default(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/conversations", json={})

    assert response.status_code == 400


async def test_send_streams_and_persists_the_turn(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await create(client)

    response = await send(client, conversation_id, "¿Qué es un CTF?\nDetalles")

    assert [e[0] for e in parse_sse(response.text)] == ["token", "token", "done"]
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["title"] == "¿Qué es un CTF?"
    assert [(m["role"], m["content"], m["status"]) for m in detail["messages"]] == [
        ("user", "¿Qué es un CTF?\nDetalles", "done"),
        ("assistant", "Hola mundo", "done"),
    ]
    assert fake_llm.calls[0][0] == "m"


async def test_history_skips_failed_turns_and_keeps_the_first_title(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await create(client)
    fake_llm.fail_before = ModelUnavailableError()
    assert (await send(client, conversation_id, "uno")).status_code == 503
    fake_llm.fail_before = None

    await send(client, conversation_id, "dos")

    _, history = fake_llm.calls[-1]
    assert [(m.role, m.content) for m in history] == [("user", "uno"), ("user", "dos")]
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["title"] == "uno"
    assert [m["status"] for m in detail["messages"]] == ["done", "error", "done", "done"]


async def test_unknown_model_is_json_404_and_saved_as_error(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await create(client)
    fake_llm.fail_before = ModelNotFoundError()

    response = await send(client, conversation_id, "hola")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"][-1]["status"] == "error"


async def test_empty_reply_is_a_json_error_and_saved_as_error(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await create(client)
    fake_llm.fail_before = EmptyReplyError()

    response = await send(client, conversation_id, "hola")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EMPTY_REPLY"
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"][-1]["status"] == "error"


async def test_mid_stream_error_keeps_partial_reply(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await create(client)
    fake_llm.fail_after = ModelUnavailableError()

    events = parse_sse((await send(client, conversation_id, "hola")).text)

    assert events[-1][0] == "error"
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"][-1] == {
        **detail["messages"][-1],
        "content": "Hola mundo",
        "status": "error",
    }


async def test_client_disconnect_saves_reply_as_stopped(fake_llm: FakeLLMProvider) -> None:
    saved: list[tuple[str, str]] = []

    async def on_finish(content: str, status: str) -> None:
        saved.append((content, status))

    response = await stream_reply(
        fake_llm, "m", [ChatMessage(role="user", content="x")], on_finish=on_finish
    )
    body = response.body_iterator
    await anext(body)  # first token reaches the client, then it goes away
    await body.aclose()  # type: ignore[attr-defined]

    assert saved == [("Hola", "stopped")]


async def test_rename_and_delete(client: httpx.AsyncClient) -> None:
    conversation_id = await create(client)

    renamed = await client.patch(
        f"/api/conversations/{conversation_id}", json={"title": "  Notas web  "}
    )
    assert renamed.json()["title"] == "Notas web"
    assert (
        await client.patch(f"/api/conversations/{conversation_id}", json={"title": "   "})
    ).status_code == 422

    assert (await client.delete(f"/api/conversations/{conversation_id}")).status_code == 204
    missing = await client.get(f"/api/conversations/{conversation_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


@pytest.mark.parametrize("bad_id", ["../etc", "ABC", "0" * 31])
async def test_rejects_malformed_ids(client: httpx.AsyncClient, bad_id: str) -> None:
    assert (await client.get(f"/api/conversations/{bad_id}")).status_code in {404, 422}


async def test_unknown_conversation(client: httpx.AsyncClient) -> None:
    assert (await send(client, "0" * 32, "hola")).status_code == 404


async def test_repository_is_shared_with_the_app(
    client: httpx.AsyncClient, repo: SqliteConversationRepository
) -> None:
    conversation_id = await create(client)

    assert await repo.get(conversation_id) is not None
