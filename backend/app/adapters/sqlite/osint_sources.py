import uuid
from datetime import UTC, datetime
from typing import cast

import aiosqlite

from app.domain.osint import OsintCategory, OsintSource, OsintSourceFields


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _source(row: aiosqlite.Row) -> OsintSource:
    return OsintSource(
        id=row["id"],
        fields=OsintSourceFields(
            name=row["name"],
            url=row["url"],
            category=cast(OsintCategory, row["category"]),
            description=row["description"],
            requires_api_key=bool(row["requires_api_key"]),
            requires_payment=bool(row["requires_payment"]),
        ),
        builtin=bool(row["builtin"]),
        is_active=bool(row["is_active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _values(fields: OsintSourceFields) -> tuple[object, ...]:
    return (
        fields.name,
        fields.url,
        fields.category,
        fields.description,
        int(fields.requires_api_key),
        int(fields.requires_payment),
    )


class SqliteOsintSourceRepository:
    """OsintSourceRepository on the shared aiosqlite connection.

    Built-ins are protected here too (`AND builtin = 0`), not only in the API layer.
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def list_all(
        self, category: OsintCategory | None = None, active_only: bool = False
    ) -> list[OsintSource]:
        where = []
        params: list[object] = []
        if category is not None:
            where.append("category = ?")
            params.append(category)
        if active_only:
            where.append("is_active = 1")
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        async with self._db.execute(
            f"SELECT * FROM osint_sources{clause}"  # noqa: S608 - fixed fragments, values bound
            " ORDER BY builtin DESC, position, created_at, id",
            params,
        ) as cursor:
            return [_source(row) for row in await cursor.fetchall()]

    async def get(self, source_id: str) -> OsintSource | None:
        async with self._db.execute(
            "SELECT * FROM osint_sources WHERE id = ?", (source_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _source(row) if row else None

    async def create(self, fields: OsintSourceFields, is_active: bool = True) -> OsintSource:
        now = _now()
        source_id = uuid.uuid4().hex
        await self._db.execute(
            "INSERT INTO osint_sources (id, name, url, category, description, requires_api_key,"
            " requires_payment, builtin, is_active, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (source_id, *_values(fields), int(is_active), now, now),
        )
        await self._db.commit()
        created = await self.get(source_id)
        if created is None:  # pragma: no cover - just inserted
            raise RuntimeError("OSINT source vanished after insert")
        return created

    async def update(
        self, source_id: str, fields: OsintSourceFields, is_active: bool
    ) -> OsintSource | None:
        cursor = await self._db.execute(
            "UPDATE osint_sources SET name = ?, url = ?, category = ?, description = ?,"
            " requires_api_key = ?, requires_payment = ?, is_active = ?, updated_at = ?"
            " WHERE id = ? AND builtin = 0",
            (*_values(fields), int(is_active), _now(), source_id),
        )
        await self._db.commit()
        return await self.get(source_id) if cursor.rowcount else None

    async def set_active(self, source_id: str, is_active: bool) -> OsintSource | None:
        cursor = await self._db.execute(
            "UPDATE osint_sources SET is_active = ?, updated_at = ? WHERE id = ?",
            (int(is_active), _now(), source_id),
        )
        await self._db.commit()
        return await self.get(source_id) if cursor.rowcount else None

    async def toggle(self, source_id: str) -> OsintSource | None:
        # One statement: two concurrent toggles can't both read the same old value.
        cursor = await self._db.execute(
            "UPDATE osint_sources SET is_active = 1 - is_active, updated_at = ? WHERE id = ?",
            (_now(), source_id),
        )
        await self._db.commit()
        return await self.get(source_id) if cursor.rowcount else None

    async def count_custom(self) -> int:
        async with self._db.execute(
            "SELECT COUNT(*) FROM osint_sources WHERE builtin = 0"
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def delete(self, source_id: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM osint_sources WHERE id = ? AND builtin = 0", (source_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def seed_builtins(self, builtins: dict[str, OsintSourceFields]) -> None:
        # Upsert the content from code; is_active is deliberately not in the UPDATE, so the
        # user's on/off choice survives restarts.
        now = _now()
        for position, (source_id, fields) in enumerate(builtins.items()):
            await self._db.execute(
                "INSERT INTO osint_sources (id, name, url, category, description,"
                " requires_api_key, requires_payment, builtin, is_active, position,"
                " created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET name = excluded.name, url = excluded.url,"
                " category = excluded.category, description = excluded.description,"
                " requires_api_key = excluded.requires_api_key,"
                " requires_payment = excluded.requires_payment, builtin = 1,"
                " position = excluded.position, updated_at = excluded.updated_at",
                (source_id, *_values(fields), position, now, now),
            )
        # Built-ins removed from the code become editable custom sources.
        placeholders = ", ".join("?" for _ in builtins) or "''"
        await self._db.execute(
            f"UPDATE osint_sources SET builtin = 0, updated_at = ?"  # noqa: S608 - placeholders only
            f" WHERE builtin = 1 AND id NOT IN ({placeholders})",
            (now, *builtins),
        )
        await self._db.commit()
