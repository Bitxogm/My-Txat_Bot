import uuid
from datetime import UTC, datetime

import aiosqlite

from app.domain.personality import GenerationParams, Personality, PersonalityFields


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _personality(row: aiosqlite.Row) -> Personality:
    return Personality(
        id=row["id"],
        fields=PersonalityFields(
            name=row["name"],
            icon=row["icon"],
            description=row["description"],
            system_prompt=row["system_prompt"],
            params=GenerationParams(
                temperature=row["temperature"], top_p=row["top_p"], num_ctx=row["num_ctx"]
            ),
            default_model=row["default_model"],
        ),
        builtin=bool(row["builtin"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _values(fields: PersonalityFields) -> tuple[object, ...]:
    return (
        fields.name,
        fields.icon,
        fields.description,
        fields.system_prompt,
        fields.params.temperature,
        fields.params.top_p,
        fields.params.num_ctx,
        fields.default_model,
    )


class SqlitePersonalityRepository:
    """PersonalityRepository on the shared aiosqlite connection.

    Built-ins are protected here too (`AND builtin = 0`), not only in the API layer.
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def list_all(self) -> list[Personality]:
        async with self._db.execute(
            "SELECT * FROM personalities ORDER BY builtin DESC, position, created_at, id"
        ) as cursor:
            return [_personality(row) for row in await cursor.fetchall()]

    async def get(self, personality_id: str) -> Personality | None:
        async with self._db.execute(
            "SELECT * FROM personalities WHERE id = ?", (personality_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _personality(row) if row else None

    async def create(self, fields: PersonalityFields) -> Personality:
        now = _now()
        personality_id = uuid.uuid4().hex
        await self._db.execute(
            "INSERT INTO personalities (id, name, icon, description, system_prompt,"
            " temperature, top_p, num_ctx, default_model, builtin, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (personality_id, *_values(fields), now, now),
        )
        await self._db.commit()
        created = await self.get(personality_id)
        if created is None:  # pragma: no cover - just inserted
            raise RuntimeError("personality vanished after insert")
        return created

    async def update(self, personality_id: str, fields: PersonalityFields) -> Personality | None:
        cursor = await self._db.execute(
            "UPDATE personalities SET name = ?, icon = ?, description = ?, system_prompt = ?,"
            " temperature = ?, top_p = ?, num_ctx = ?, default_model = ?, updated_at = ?"
            " WHERE id = ? AND builtin = 0",
            (*_values(fields), _now(), personality_id),
        )
        await self._db.commit()
        return await self.get(personality_id) if cursor.rowcount else None

    async def delete(self, personality_id: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM personalities WHERE id = ? AND builtin = 0", (personality_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def seed_builtins(self, builtins: dict[str, PersonalityFields]) -> None:
        # Upsert: content from code wins (fixes reach the DB), created_at is kept. Conversations
        # keep their own snapshot, so refreshing a built-in never changes past conversations.
        now = _now()
        for position, (personality_id, fields) in enumerate(builtins.items()):
            await self._db.execute(
                "INSERT INTO personalities (id, name, icon, description, system_prompt,"
                " temperature, top_p, num_ctx, default_model, builtin, position,"
                " created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET name = excluded.name, icon = excluded.icon,"
                " description = excluded.description, system_prompt = excluded.system_prompt,"
                " temperature = excluded.temperature, top_p = excluded.top_p,"
                " num_ctx = excluded.num_ctx, default_model = excluded.default_model,"
                " builtin = 1, position = excluded.position, updated_at = excluded.updated_at",
                (personality_id, *_values(fields), position, now, now),
            )
        # A built-in removed from the code becomes a normal, editable personality instead of a
        # read-only leftover (deleting it would also drop it from the user's list).
        placeholders = ", ".join("?" for _ in builtins) or "''"
        await self._db.execute(
            f"UPDATE personalities SET builtin = 0, updated_at = ?"  # noqa: S608 - placeholders only
            f" WHERE builtin = 1 AND id NOT IN ({placeholders})",
            (now, *builtins),
        )
        await self._db.commit()
