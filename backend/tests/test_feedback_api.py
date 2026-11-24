import json

import aiosqlite
import httpx
import pytest

from app.adapters.sqlite.conversations import SqliteConversationRepository
from app.domain.feedback import MAX_CORRECTION_CHARS
from app.domain.prompts import BASE_PROMPT_VERSION
from tests.conftest import FakeLLMProvider
from tests.test_conversations_api import parse_sse

EXPORT_KEYS = {
    "question",
    "question_files",
    "answer",
    "rating",
    "reasons",
    "correction",
    "model",
    "model_approximate",
    "provider",
    "personality",
    "base_prompt_version",
    "created_at",
    "updated_at",
}


async def conversation(client: httpx.AsyncClient, model: str = "m") -> str:
    response = await client.post("/api/conversations", json={"model": model})
    assert response.status_code == 201
    return str(response.json()["id"])


async def ask(
    client: httpx.AsyncClient, conversation_id: str, content: str = "¿Qué es nmap?"
) -> int:
    """Send a message and return the id of the saved reply (from the `done` event)."""
    response = await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": content}
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1][0] == "done"
    return int(events[-1][1]["message_id"])  # type: ignore[call-overload]


async def detail(client: httpx.AsyncClient, conversation_id: str) -> list[dict[str, object]]:
    messages = (await client.get(f"/api/conversations/{conversation_id}")).json()["messages"]
    return list(messages)


async def rate(client: httpx.AsyncClient, message_id: int, **body: object) -> httpx.Response:
    return await client.put(f"/api/messages/{message_id}/feedback", json=body)


async def test_done_event_carries_the_saved_message_id(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await conversation(client)

    reply_id = await ask(client, conversation_id)

    messages = await detail(client, conversation_id)
    assert messages[1]["id"] == reply_id
    assert messages[1]["role"] == "assistant"
    assert messages[1]["feedback"] is None


async def test_thumbs_up_is_saved_with_a_copy_of_the_turn(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await conversation(client)
    reply_id = await ask(client, conversation_id, "¿Qué es nmap?")

    response = await rate(client, reply_id, rating=1)

    assert response.status_code == 200
    body = response.json()
    assert body["rating"] == 1
    assert body["reasons"] == []
    assert body["correction"] is None
    assert body["question"] == "¿Qué es nmap?"
    assert body["answer"] == "Hola mundo"
    assert body["model"] == "m"
    assert body["model_approximate"] is False
    assert body["provider"] == "ollama"
    assert body["personality"] == "General"
    assert body["base_prompt_version"] == BASE_PROMPT_VERSION
    messages = await detail(client, conversation_id)
    assert messages[1]["feedback"] == {"rating": 1, "reasons": [], "correction": None}


async def test_thumbs_down_with_reasons_and_correction(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await conversation(client)
    reply_id = await ask(client, conversation_id)

    response = await rate(
        client,
        reply_id,
        rating=-1,
        reasons=["incorrect", "wrong_command"],
        correction="  nmap es un escáner de puertos.\n\nnmap -sV <ip>  ",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reasons"] == ["incorrect", "wrong_command"]
    # Kept as plain text, only trimmed at the ends.
    assert body["correction"] == "nmap es un escáner de puertos.\n\nnmap -sV <ip>"


async def test_rating_can_be_changed_and_keeps_its_creation_date(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await conversation(client)
    reply_id = await ask(client, conversation_id)
    first = (await rate(client, reply_id, rating=-1, reasons=["incomplete"])).json()

    second = (await rate(client, reply_id, rating=1)).json()

    assert second["rating"] == 1
    assert second["reasons"] == []
    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] >= first["updated_at"]
    assert (await client.get("/api/feedback")).json()["total"] == 1


async def test_rating_can_be_removed(client: httpx.AsyncClient, fake_llm: FakeLLMProvider) -> None:
    conversation_id = await conversation(client)
    reply_id = await ask(client, conversation_id)
    await rate(client, reply_id, rating=1)

    assert (await client.delete(f"/api/messages/{reply_id}/feedback")).status_code == 204
    assert (await detail(client, conversation_id))[1]["feedback"] is None
    response = await client.delete(f"/api/messages/{reply_id}/feedback")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FEEDBACK_NOT_FOUND"


async def test_deleting_the_conversation_deletes_its_ratings(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider, db: aiosqlite.Connection
) -> None:
    conversation_id = await conversation(client)
    reply_id = await ask(client, conversation_id)
    await rate(client, reply_id, rating=-1, correction="Otra cosa")
    other = await conversation(client)
    await rate(client, await ask(client, other), rating=1)

    assert (await client.delete(f"/api/conversations/{conversation_id}")).status_code == 204

    body = (await client.get("/api/feedback")).json()
    assert body["total"] == 1
    assert body["items"][0]["conversation_id"] == other
    async with db.execute("SELECT COUNT(*) FROM message_feedback") as cursor:
        row = await cursor.fetchone()
    assert row is not None and row[0] == 1


async def test_user_messages_cannot_be_rated(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await conversation(client)
    reply_id = await ask(client, conversation_id)

    response = await rate(client, reply_id - 1, rating=1)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FEEDBACK_NOT_ALLOWED"


async def test_failed_replies_cannot_be_rated_but_stopped_ones_can(
    client: httpx.AsyncClient, repo: SqliteConversationRepository
) -> None:
    conversation_id = await conversation(client)
    await repo.add_message(conversation_id, "user", "hola", "done")
    failed = await repo.add_message(conversation_id, "assistant", "a medias", "error")
    empty = await repo.add_message(conversation_id, "assistant", "  ", "done")
    stopped = await repo.add_message(conversation_id, "assistant", "a medias", "stopped")

    for message in (failed, empty):
        response = await rate(client, message.id, rating=1)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FEEDBACK_NOT_ALLOWED"
    assert (await rate(client, stopped.id, rating=1)).status_code == 200


async def test_unknown_message(client: httpx.AsyncClient) -> None:
    response = await rate(client, 999_999, rating=1)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MESSAGE_NOT_FOUND"
    assert response.json()["error"]["request_id"]


async def test_correction_length_limit(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    reply_id = await ask(client, await conversation(client))

    ok = await rate(client, reply_id, rating=-1, correction="x" * MAX_CORRECTION_CHARS)
    too_long = await rate(client, reply_id, rating=-1, correction="x" * (MAX_CORRECTION_CHARS + 1))

    assert ok.status_code == 200
    assert too_long.status_code == 422
    assert set(too_long.json()["error"]) == {"code", "message", "request_id"}
    stored = (await client.get("/api/feedback")).json()["items"][0]["correction"]
    assert len(stored) == MAX_CORRECTION_CHARS


@pytest.mark.parametrize(
    "body",
    [
        {"rating": 0},
        {"rating": 2},
        {"rating": -1, "reasons": ["inventado"]},
        {"rating": -1, "reasons": ["incorrect", "incorrect"]},
        {"rating": -1, "correction": "hola\x00"},
        {"rating": 1, "reasons": ["incorrect"]},
        {"rating": 1, "correction": "no aplica a 👍"},
        {"rating": 1, "extra": True},
        {},
    ],
)
async def test_invalid_bodies(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider, body: dict[str, object]
) -> None:
    reply_id = await ask(client, await conversation(client))

    response = await client.put(f"/api/messages/{reply_id}/feedback", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_an_empty_correction_is_stored_as_none(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    reply_id = await ask(client, await conversation(client))

    body = (await rate(client, reply_id, rating=-1, correction="   \n ")).json()

    assert body["correction"] is None


async def test_older_replies_get_an_approximate_model_and_unknown_base_layer(
    client: httpx.AsyncClient, repo: SqliteConversationRepository
) -> None:
    conversation_id = await conversation(client, model="groq/openai/gpt-oss-120b")
    await repo.add_message(conversation_id, "user", "hola", "done")
    # Saved without its generation, like replies from before it was recorded.
    old = await repo.add_message(conversation_id, "assistant", "respuesta", "done")

    body = (await rate(client, old.id, rating=1)).json()

    assert body["model"] == "groq/openai/gpt-oss-120b"
    assert body["model_approximate"] is True
    assert body["base_prompt_version"] is None


async def test_the_question_lists_its_files_but_not_their_contents(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await conversation(client)
    upload = await client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={"file": ("scan.txt", b"22/tcp open ssh secreto", "text/plain")},
    )
    assert upload.status_code == 201
    response = await client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "¿Qué ves?", "attachment_ids": [upload.json()["id"]]},
    )
    reply_id = int(parse_sse(response.text)[-1][1]["message_id"])  # type: ignore[call-overload]

    body = (await rate(client, reply_id, rating=1)).json()

    assert body["question"] == "¿Qué ves?"
    assert body["question_files"] == ["scan.txt"]
    export = (await client.get("/api/feedback/export")).text
    assert "secreto" not in export


async def test_list_filters_and_pagination(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    first = await conversation(client)
    up = await ask(client, first)
    await rate(client, up, rating=1)
    second = await conversation(client, model="otro")
    down = await ask(client, second)
    await rate(client, down, rating=-1, reasons=["too_long", "other"])

    async def total(query: str) -> int:
        response = await client.get(f"/api/feedback?{query}")
        assert response.status_code == 200, response.text
        return int(response.json()["total"])

    assert await total("") == 2
    assert await total("rating=1") == 1
    assert await total("rating=-1") == 1
    assert await total("model=otro") == 1
    assert await total("personality=General") == 2
    assert await total("personality=Pentester") == 0
    assert await total("reason=too_long") == 1
    assert await total("reason=incorrect") == 0
    assert await total(f"conversation_id={first}") == 1
    assert await total("from=2000-01-01&to=2999-12-31") == 2
    assert await total("to=2000-01-01") == 0
    page = (await client.get("/api/feedback?limit=1&offset=1")).json()
    assert page["total"] == 2
    assert [item["message_id"] for item in page["items"]] == [up]  # newest first


@pytest.mark.parametrize(
    "query",
    ["rating=0", "rating=x", "reason=nope", "limit=0", "limit=201", "offset=-1", "from=ayer"],
)
async def test_list_rejects_bad_filters(client: httpx.AsyncClient, query: str) -> None:
    response = await client.get(f"/api/feedback?{query}")

    assert response.status_code == 422


async def test_export_is_jsonl_with_only_the_rating_fields(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    first = await ask(client, await conversation(client), "uno")
    await rate(client, first, rating=1)
    second = await ask(client, await conversation(client), "dos")
    await rate(client, second, rating=-1, reasons=["incorrect"], correction="la buena")

    response = await client.get("/api/feedback/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["content-disposition"].startswith("attachment; filename=")
    assert response.headers["cache-control"] == "no-store"
    lines = response.text.splitlines()
    rows = [json.loads(line) for line in lines]
    assert [set(row) for row in rows] == [EXPORT_KEYS, EXPORT_KEYS]
    assert [row["question"] for row in rows] == ["uno", "dos"]  # oldest first
    assert rows[1]["correction"] == "la buena"
    assert rows[1]["reasons"] == ["incorrect"]
    filtered = (await client.get("/api/feedback/export?rating=-1")).text.splitlines()
    assert [json.loads(line)["question"] for line in filtered] == ["dos"]


async def test_export_without_ratings_is_empty(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/feedback/export")

    assert response.status_code == 200
    assert response.text == ""


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", "/api/messages/1/feedback"),
        ("DELETE", "/api/messages/1/feedback"),
        ("GET", "/api/feedback"),
        ("GET", "/api/feedback/export"),
    ],
)
async def test_every_endpoint_needs_a_session(
    anon_client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await anon_client.request(method, path, json={"rating": 1})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("bad_id", ["0", "-1", "abc", str(2**63)])
async def test_rejects_malformed_message_ids(client: httpx.AsyncClient, bad_id: str) -> None:
    response = await client.put(f"/api/messages/{bad_id}/feedback", json={"rating": 1})

    assert response.status_code == 422
