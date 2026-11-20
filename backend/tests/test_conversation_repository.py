import asyncio
from pathlib import Path

import pytest

from app.adapters.sqlite.conversations import SqliteConversationRepository
from app.adapters.sqlite.database import MIGRATIONS, connect, sqlite_path
from app.domain.conversation import title_from_message


async def test_create_list_and_order_by_activity(repo: SqliteConversationRepository) -> None:
    first = await repo.create("Uno", "m")
    second = await repo.create("Dos", "m")
    assert [c.id for c in await repo.list_all()] == [second.id, first.id]

    await asyncio.sleep(0.001)
    await repo.add_message(first.id, "user", "hola", "done")

    assert [c.id for c in await repo.list_all()] == [first.id, second.id]


async def test_rename_does_not_reorder(repo: SqliteConversationRepository) -> None:
    old = await repo.create("Old", "m")
    new = await repo.create("New", "m")

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
