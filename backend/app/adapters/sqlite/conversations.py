import uuid
from datetime import UTC, datetime
from typing import cast

import aiosqlite

from app.domain.chat import Role
from app.domain.conversation import Conversation, MessageStatus, StoredMessage


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _conversation(row: aiosqlite.Row) -> Conversation:
    return Conversation(
        id=row["id"],
        title=row["title"],
        model=row["model"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _message(row: aiosqlite.Row) -> StoredMessage:
    return StoredMessage(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=cast(Role, row["role"]),
        content=row["content"],
        status=cast(MessageStatus, row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SqliteConversationRepository:
    """ConversationRepository on a single aiosqlite connection (one user, low concurrency)."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, title: str, model: str) -> Conversation:
        now = _now()
        conversation_id = uuid.uuid4().hex
        await self._db.execute(
            "INSERT INTO conversations (id, title, model, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (conversation_id, title, model, now, now),
        )
        await self._db.commit()
        created = await self.get(conversation_id)
        if created is None:  # pragma: no cover - just inserted
            raise RuntimeError("conversation vanished after insert")
        return created

    async def list_all(self) -> list[Conversation]:
        async with self._db.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC, id"
        ) as cursor:
            return [_conversation(row) for row in await cursor.fetchall()]

    async def get(self, conversation_id: str) -> Conversation | None:
        async with self._db.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _conversation(row) if row else None

    async def update(
        self, conversation_id: str, *, title: str | None = None, model: str | None = None
    ) -> Conversation | None:
        # updated_at tracks activity (new messages), so renaming doesn't reorder the list.
        await self._db.execute(
            "UPDATE conversations SET title = COALESCE(?, title), model = COALESCE(?, model)"
            " WHERE id = ?",
            (title, model, conversation_id),
        )
        await self._db.commit()
        return await self.get(conversation_id)

    async def delete(self, conversation_id: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def messages(self, conversation_id: str) -> list[StoredMessage]:
        async with self._db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        ) as cursor:
            return [_message(row) for row in await cursor.fetchall()]

    async def add_message(
        self, conversation_id: str, role: Role, content: str, status: MessageStatus
    ) -> StoredMessage:
        now = _now()
        cursor = await self._db.execute(
            "INSERT INTO messages (conversation_id, role, content, status, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, status, now),
        )
        await self._db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
        )
        await self._db.commit()
        return StoredMessage(
            id=int(cursor.lastrowid or 0),
            conversation_id=conversation_id,
            role=role,
            content=content,
            status=status,
            created_at=datetime.fromisoformat(now),
        )
