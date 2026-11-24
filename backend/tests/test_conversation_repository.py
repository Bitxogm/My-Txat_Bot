import asyncio
from pathlib import Path

import pytest

from app.adapters.sqlite.conversations import SqliteConversationRepository
from app.adapters.sqlite.database import MIGRATIONS, connect, sqlite_path
from app.domain.conversation import Generation, title_from_message


async def test_create_list_and_order_by_activity(repo: SqliteConversationRepository) -> None:
    first = await repo.create("Uno", "m")
    second = await repo.create("Dos", "m")
    await repo.add_message(first.id, "user", "uno", "done")
    await asyncio.sleep(0.001)
    await repo.add_message(second.id, "user", "dos", "done")
    assert [c.id for c in await repo.list_all()] == [second.id, first.id]

    await asyncio.sleep(0.001)
    await repo.add_message(first.id, "user", "hola", "done")

    assert [c.id for c in await repo.list_all()] == [first.id, second.id]


async def test_rename_does_not_reorder(repo: SqliteConversationRepository) -> None:
    old = await repo.create("Old", "m")
    new = await repo.create("New", "m")
    await repo.add_message(old.id, "user", "a", "done")
    await asyncio.sleep(0.001)
    await repo.add_message(new.id, "user", "b", "done")

    renamed = await repo.update(old.id, title="Renombrada")

    assert renamed is not None
    assert renamed.title == "Renombrada"
    assert [c.id for c in await repo.list_all()] == [new.id, old.id]


async def test_messages_in_order_and_cascade_delete(repo: SqliteConversationRepository) -> None:
    conversation = await repo.create("T", "m")
    await repo.add_message(conversation.id, "user", "a", "done")
    await repo.add_message(conversation.id, "assistant", "b", "stopped")

    messages = await repo.messages(conversation.id)
    assert [(m.role, m.content, m.status) for m in messages] == [
        ("user", "a", "done"),
        ("assistant", "b", "stopped"),
    ]

    assert await repo.delete(conversation.id) is True
    assert await repo.get(conversation.id) is None
    assert await repo.messages(conversation.id) == []
    assert await repo.delete(conversation.id) is False


async def test_migrations_are_idempotent_on_disk(tmp_path: Path) -> None:
    path = str(tmp_path / "nested" / "txat.db")
    db = await connect(path)
    repo = SqliteConversationRepository(db)
    created = await repo.create("Persistente", "m")
    await db.close()

    db = await connect(path)
    async with db.execute("PRAGMA user_version") as cursor:
        row = await cursor.fetchone()
    assert row is not None and row[0] == len(MIGRATIONS)
    assert await SqliteConversationRepository(db).get(created.id) is not None
    await db.close()


@pytest.mark.parametrize(
    ("url", "path"),
    [("sqlite:///./data/txatbot.db", "./data/txatbot.db"), ("sqlite:////app/x.db", "/app/x.db")],
)
def test_sqlite_path(url: str, path: str) -> None:
    assert sqlite_path(url) == path


@pytest.mark.parametrize("url", ["postgres://x", "sqlite:///"])
def test_sqlite_path_rejects_bad_urls(url: str) -> None:
    with pytest.raises(ValueError):
        sqlite_path(url)


@pytest.mark.parametrize(
    ("content", "title"),
    [
        ("  hola   mundo \nsegunda línea", "hola mundo"),
        ("x" * 100, "x" * 79 + "…"),
        ("   ", "Nueva conversación"),
    ],
)
def test_title_from_message(content: str, title: str) -> None:
    assert title_from_message(content) == title


# --- drafts (ADR-022) ------------------------------------------------------------------------


async def test_drafts_are_not_listed(repo: SqliteConversationRepository) -> None:
    draft = await repo.create("Borrador", "m")
    replied_only = await repo.create("Solo respuesta", "m")
    await repo.add_message(replied_only.id, "assistant", "x", "error")
    real = await repo.create("Real", "m")
    await repo.add_message(real.id, "user", "hola", "done")

    assert [c.id for c in await repo.list_all()] == [real.id]
    assert await repo.get(draft.id) is not None  # still reachable by id


async def test_personality_changes_only_while_draft(repo: SqliteConversationRepository) -> None:
    from app.domain.conversation import PersonalitySnapshot

    # No personalities table rows here (FK): snapshots without id, told apart by name.
    conversation = await repo.create("T", "m", PersonalitySnapshot(name="General"))
    pentester = PersonalitySnapshot(name="Pentester", system_prompt="p")

    assert await repo.set_personality_if_draft(conversation.id, pentester) is True
    changed = await repo.get(conversation.id)
    assert changed is not None and changed.personality.name == "Pentester"

    await repo.add_message(conversation.id, "user", "hola", "done")
    assert await repo.set_personality_if_draft(conversation.id, PersonalitySnapshot()) is False


async def test_stale_drafts(repo: SqliteConversationRepository) -> None:
    from datetime import UTC, datetime, timedelta

    draft = await repo.create("Borrador", "m")
    used = await repo.create("Usada", "m")
    await repo.add_message(used.id, "user", "hola", "done")

    assert await repo.stale_drafts(datetime.now(UTC) - timedelta(hours=1)) == []
    assert await repo.stale_drafts(datetime.now(UTC) + timedelta(seconds=1)) == [draft.id]


async def test_a_reply_keeps_what_generated_it(repo: SqliteConversationRepository) -> None:
    conversation = await repo.create("t", "m")
    generation = Generation(model="groq/x", provider="groq", base_prompt_version="abcd1234")

    user = await repo.add_message(conversation.id, "user", "hola", "done")
    reply = await repo.add_message(conversation.id, "assistant", "r", "done", generation)

    stored = await repo.messages(conversation.id)
    assert [m.generation for m in stored] == [None, generation]
    assert await repo.get_message(reply.id) == stored[1]
    assert await repo.previous_user_message(conversation.id, reply.id) == user
    assert await repo.previous_user_message(conversation.id, user.id) is None
