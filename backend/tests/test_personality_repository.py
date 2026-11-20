from pathlib import Path

import aiosqlite

from app.adapters.sqlite.conversations import SqliteConversationRepository
from app.adapters.sqlite.database import MIGRATIONS, connect, migrate
from app.adapters.sqlite.personalities import SqlitePersonalityRepository
from app.domain.builtin_personalities import BUILTIN_PERSONALITIES, MENTOR_CTF
from app.domain.personality import DEFAULT_PERSONALITY_ID, GenerationParams, PersonalityFields


def fields(name: str = "Mía") -> PersonalityFields:
    return PersonalityFields(
        name=name,
        icon="bot",
        description="",
        system_prompt="Sé breve.",
        params=GenerationParams(temperature=0.1),
    )


async def test_seed_is_idempotent_and_keeps_created_at(
    personality_repo: SqlitePersonalityRepository,
) -> None:
    before = {p.id: p.created_at for p in await personality_repo.list_all()}

    await personality_repo.seed_builtins(BUILTIN_PERSONALITIES)
    await personality_repo.seed_builtins(BUILTIN_PERSONALITIES)

    after = await personality_repo.list_all()
    assert [p.id for p in after] == list(BUILTIN_PERSONALITIES)
    assert all(p.builtin for p in after)
    assert {p.id: p.created_at for p in after} == before


async def test_seed_refreshes_builtin_content_from_code(
    personality_repo: SqlitePersonalityRepository,
) -> None:
    changed = {DEFAULT_PERSONALITY_ID: fields("Mentor renombrado")}

    await personality_repo.seed_builtins(changed)

    mentor = await personality_repo.get(DEFAULT_PERSONALITY_ID)
    assert mentor is not None
    assert mentor.fields.name == "Mentor renombrado"
    assert mentor.builtin


async def test_builtins_first_then_copies(personality_repo: SqlitePersonalityRepository) -> None:
    mine = await personality_repo.create(fields())

    listed = [p.id for p in await personality_repo.list_all()]

    assert listed[:8] == list(BUILTIN_PERSONALITIES)
    assert listed[8] == mine.id
    assert not mine.builtin


async def test_repository_refuses_to_touch_builtins(
    personality_repo: SqlitePersonalityRepository,
) -> None:
    assert await personality_repo.update(DEFAULT_PERSONALITY_ID, fields()) is None
    assert await personality_repo.delete(DEFAULT_PERSONALITY_ID) is False
    mentor = await personality_repo.get(DEFAULT_PERSONALITY_ID)
    assert mentor is not None and mentor.fields == MENTOR_CTF


async def test_deleting_a_personality_keeps_the_conversation_snapshot(
    db: aiosqlite.Connection, personality_repo: SqlitePersonalityRepository
) -> None:
    from app.domain.conversation import PersonalitySnapshot

    mine = await personality_repo.create(fields())
    conversations = SqliteConversationRepository(db)
    conversation = await conversations.create(
        "t",
        "m",
        PersonalitySnapshot(
            id=mine.id,
            name="Mía",
            icon="bot",
            system_prompt="Sé breve.",
            params=GenerationParams(temperature=0.1),
        ),
    )

    await personality_repo.delete(mine.id)

    reloaded = await conversations.get(conversation.id)
    assert reloaded is not None
    assert reloaded.personality.id is None  # ON DELETE SET NULL
    assert reloaded.personality.name == "Mía"
    assert reloaded.personality.system_prompt == "Sé breve."
    assert reloaded.personality.params.temperature == 0.1


async def test_migration_v1_to_v2_keeps_existing_conversations(tmp_path: Path) -> None:
    path = str(tmp_path / "old.db")
    old = await aiosqlite.connect(path)
    await old.executescript(f"BEGIN;\n{MIGRATIONS[0]}\nPRAGMA user_version = 1;\nCOMMIT;")
    await old.execute(
        "INSERT INTO conversations VALUES ('a' || hex(randomblob(15)), 'vieja', 'llama3',"
        " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
    )
    await old.commit()
    await old.close()

    db = await connect(path)
    try:
        async with db.execute("PRAGMA user_version") as cursor:
            row = await cursor.fetchone()
        assert row is not None and row[0] == len(MIGRATIONS)
        [old_conversation] = await SqliteConversationRepository(db).list_all()
        assert old_conversation.title == "vieja"
        assert old_conversation.personality.id is None
        assert old_conversation.personality.system_prompt == ""
        await migrate(db)  # running it again is a no-op
    finally:
        await db.close()


async def test_builtins_removed_from_code_become_editable(
    personality_repo: SqlitePersonalityRepository,
) -> None:
    remaining = dict(list(BUILTIN_PERSONALITIES.items())[:-1])

    await personality_repo.seed_builtins(remaining)

    dropped = await personality_repo.get("builtin-auditor-huella")
    assert dropped is not None and dropped.builtin is False
    assert await personality_repo.update("builtin-auditor-huella", fields()) is not None
    assert all(p.builtin for p in await personality_repo.list_all() if p.id in remaining)
