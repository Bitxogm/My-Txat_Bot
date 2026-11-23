from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.core.errors import ModelRateLimitedError
from app.maintenance import sweep_stale_drafts
from tests.conftest import FakeLLMProvider


async def new_conversation(client: httpx.AsyncClient) -> str:
    return str((await client.post("/api/conversations", json={"model": "m"})).json()["id"])


async def listed(client: httpx.AsyncClient) -> list[str]:
    body = (await client.get("/api/conversations")).json()
    return [c["id"] for c in body["conversations"]]


async def test_a_draft_can_change_its_personality(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client)

    response = await client.patch(
        f"/api/conversations/{conversation_id}", json={"personality_id": "builtin-pentester"}
    )

    assert response.status_code == 200
    assert response.json()["personality"]["name"] == "Pentester"


async def test_after_the_first_message_the_personality_is_locked(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await new_conversation(client)
    await client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "hola"})

    response = await client.patch(
        f"/api/conversations/{conversation_id}", json={"personality_id": "builtin-pentester"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PERSONALITY_LOCKED"
    # The title can still be renamed.
    renamed = await client.patch(f"/api/conversations/{conversation_id}", json={"title": "x"})
    assert renamed.status_code == 200


async def test_bad_patches(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client)

    empty = await client.patch(f"/api/conversations/{conversation_id}", json={})
    unknown = await client.patch(
        f"/api/conversations/{conversation_id}", json={"personality_id": "builtin-nope"}
    )
    extra = await client.patch(f"/api/conversations/{conversation_id}", json={"system_prompt": "x"})

    assert empty.status_code == 422
    assert unknown.status_code == 404
    assert extra.status_code == 422


async def test_a_failed_first_message_leaves_no_visible_conversation(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await new_conversation(client)
    fake_llm.fail_before = ModelRateLimitedError.for_provider("groq", 5)

    response = await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": "hola"}
    )

    assert response.status_code == 429
    assert await listed(client) == []  # a draft: still there, never shown


async def test_stale_drafts_and_their_files_are_swept(
    app: FastAPI, client: httpx.AsyncClient, fake_llm: FakeLLMProvider, tmp_path: Path
) -> None:
    old_draft = await new_conversation(client)
    await client.post(
        f"/api/conversations/{old_draft}/attachments",
        files={"file": ("a.txt", b"hola", "text/plain")},
    )
    used = await new_conversation(client)
    await client.post(f"/api/conversations/{used}/messages", json={"content": "hola"})
    state = app.state

    # Too young: kept.
    assert await sweep_stale_drafts(state.conversations, state.attachments, state.file_storage) == 0

    later = datetime.now(UTC) + timedelta(hours=25)
    removed = await sweep_stale_drafts(
        state.conversations, state.attachments, state.file_storage, now=later
    )

    assert removed == 1
    assert (await client.get(f"/api/conversations/{old_draft}")).status_code == 404
    assert (await client.get(f"/api/conversations/{used}")).status_code == 200
    assert list((tmp_path / "uploads").iterdir()) == []


async def test_a_personality_change_during_the_first_send_undoes_it(
    app: FastAPI, client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    from app.domain.conversation import PersonalitySnapshot

    conversation_id = await new_conversation(client)
    original = fake_llm.supports_vision

    async def change_meanwhile(model: str) -> bool:
        # The PATCH lands while send_message awaits a slow step, after reading the snapshot.
        await app.state.conversations.set_personality_if_draft(
            conversation_id, PersonalitySnapshot(id="builtin-pentester", name="Pentester")
        )
        return await original(model)

    fake_llm.supports_vision = change_meanwhile  # type: ignore[method-assign]

    response = await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": "hola"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PERSONALITY_LOCKED"
    assert fake_llm.calls == []  # never answered with the old personality
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"] == [] and detail["personality"]["name"] == "Pentester"


async def test_sweep_works_with_any_timezone(app: FastAPI, client: httpx.AsyncClient) -> None:
    from datetime import timezone

    await new_conversation(client)
    state = app.state
    madrid_like = timezone(timedelta(hours=1))
    later = (datetime.now(UTC) + timedelta(hours=25)).astimezone(madrid_like)

    assert (
        await sweep_stale_drafts(
            state.conversations, state.attachments, state.file_storage, now=later
        )
        == 1
    )
