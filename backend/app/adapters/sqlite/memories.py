import uuid
from datetime import UTC, datetime
from typing import cast

import aiosqlite

from app.domain.memory import IN_PROGRESS_MAX_AGE, Memory, MemoryCategory


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _now() -> str:
    return _iso(datetime.now(UTC))


def _memory(row: aiosqlite.Row) -> Memory:
    return Memory(
        id=row["id"],
        category=cast(MemoryCategory, row["category"]),
        text=row["text"],
        is_active=bool(row["is_active"]),
        archived_at=datetime.fromisoformat(row["archived_at"]) if row["archived_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class SqliteMemoryRepository:
    """MemoryRepository on the shared aiosqlite connection."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def _archive_expired(self, now: datetime) -> None:
        # On read, not at startup: the server can run for weeks without restarting.
        await self._db.execute(
            "UPDATE memories SET archived_at = ? WHERE category = 'in_progress'"
            " AND archived_at IS NULL AND updated_at < ?",
            (_iso(now), _iso(now - IN_PROGRESS_MAX_AGE)),
        )
        await self._db.commit()

    async def list_all(self, now: datetime) -> list[Memory]:
        await self._archive_expired(now)
        async with self._db.execute("SELECT * FROM memories ORDER BY created_at, id") as cursor:
            return [_memory(row) for row in await cursor.fetchall()]

    async def in_use(self, now: datetime) -> list[Memory]:
        await self._archive_expired(now)
        async with self._db.execute(
            "SELECT * FROM memories WHERE is_active = 1 AND archived_at IS NULL"
            " ORDER BY created_at, id"
        ) as cursor:
            return [_memory(row) for row in await cursor.fetchall()]

    async def get(self, memory_id: str) -> Memory | None:
        async with self._db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)) as cur:
            row = await cur.fetchone()
        return _memory(row) if row else None

    async def create(self, category: MemoryCategory, text: str, is_active: bool) -> Memory:
        now = _now()
        memory_id = uuid.uuid4().hex
        await self._db.execute(
            "INSERT INTO memories (id, category, text, is_active, archived_at, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, NULL, ?, ?)",
            (memory_id, category, text, int(is_active), now, now),
        )
        await self._db.commit()
        created = await self.get(memory_id)
        if created is None:  # pragma: no cover - just inserted
            raise RuntimeError("memory vanished after insert")
        return created

    async def replace(
        self, memory_id: str, category: MemoryCategory, text: str, is_active: bool
    ) -> Memory | None:
        cursor = await self._db.execute(
            "UPDATE memories SET category = ?, text = ?, is_active = ?, archived_at = NULL,"
            " updated_at = ? WHERE id = ?",
            (category, text, int(is_active), _now(), memory_id),
        )
        await self._db.commit()
        return await self.get(memory_id) if cursor.rowcount else None

    async def delete(self, memory_id: str) -> bool:
        cursor = await self._db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        await self._db.commit()
        return cursor.rowcount > 0


_MEMORY_TO_REMOTE = "memory_to_remote"


class SqliteAppSettingsRepository:
    """Small key/value store for settings changed from the UI (not deployment config)."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def memory_to_remote(self) -> bool:
        async with self._db.execute(
            "SELECT value FROM app_settings WHERE key = ?", (_MEMORY_TO_REMOTE,)
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None and row["value"] == "true"

    async def set_memory_to_remote(self, enabled: bool) -> None:
        await self._db.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (_MEMORY_TO_REMOTE, "true" if enabled else "false"),
        )
        await self._db.commit()
