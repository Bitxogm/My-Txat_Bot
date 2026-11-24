import uuid
from datetime import UTC, datetime
from typing import cast

import aiosqlite

from app.domain.chat import Role
from app.domain.conversation import (
    Conversation,
    Generation,
    MessageStatus,
    PersonalitySnapshot,
    StoredMessage,
)
from app.domain.personality import GenerationParams


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _conversation(row: aiosqlite.Row) -> Conversation:
    return Conversation(
        id=row["id"],
        title=row["title"],
        model=row["model"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        personality=PersonalitySnapshot(
            id=row["personality_id"],
            name=row["personality_name"],
            icon=row["personality_icon"],
            system_prompt=row["system_prompt"],
            params=GenerationParams(
                temperature=row["temperature"], top_p=row["top_p"], num_ctx=row["num_ctx"]
            ),
        ),
    )


def _message(row: aiosqlite.Row) -> StoredMessage:
    return StoredMessage(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=cast(Role, row["role"]),
        content=row["content"],
        status=cast(MessageStatus, row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        generation=(
            Generation(
                model=row["model"],
                provider=row["provider"] or "",
                base_prompt_version=row["base_prompt_version"] or "",
            )
            if row["model"]
            else None
        ),
    )


class SqliteConversationRepository:
    """ConversationRepository on a single aiosqlite connection (one user, low concurrency)."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(
        self, title: str, model: str, personality: PersonalitySnapshot | None = None
    ) -> Conversation:
        now = _now()
        conversation_id = uuid.uuid4().hex
        snap = personality or PersonalitySnapshot()
        await self._db.execute(
            "INSERT INTO conversations (id, title, model, created_at, updated_at,"
            " personality_id, personality_name, personality_icon, system_prompt,"
            " temperature, top_p, num_ctx)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                title,
                model,
                now,
                now,
                snap.id,
                snap.name,
                snap.icon,
                snap.system_prompt,
                snap.params.temperature,
                snap.params.top_p,
                snap.params.num_ctx,
            ),
        )
        await self._db.commit()
        created = await self.get(conversation_id)
        if created is None:  # pragma: no cover - just inserted
            raise RuntimeError("conversation vanished after insert")
        return created

    async def list_all(self) -> list[Conversation]:
        # Drafts (no user message yet, ADR-022) are not listed: they only exist to hold files
        # attached before the first message, or a first message that failed.
        async with self._db.execute(
            "SELECT * FROM conversations c WHERE EXISTS ("
            " SELECT 1 FROM messages m WHERE m.conversation_id = c.id AND m.role = 'user')"
            " ORDER BY updated_at DESC, id"
        ) as cursor:
            return [_conversation(row) for row in await cursor.fetchall()]

    async def set_personality_if_draft(
        self, conversation_id: str, personality: PersonalitySnapshot
    ) -> bool:
        """Replace the personality snapshot only while there is no user message (atomically).
        Returns whether it changed."""
        snap = personality
        cursor = await self._db.execute(
            "UPDATE conversations SET personality_id = ?, personality_name = ?,"
            " personality_icon = ?, system_prompt = ?, temperature = ?, top_p = ?, num_ctx = ?"
            " WHERE id = ? AND NOT EXISTS ("
            " SELECT 1 FROM messages m WHERE m.conversation_id = ? AND m.role = 'user')",
            (
                snap.id,
                snap.name,
                snap.icon,
                snap.system_prompt,
                snap.params.temperature,
                snap.params.top_p,
                snap.params.num_ctx,
                conversation_id,
                conversation_id,
            ),
        )
        await self._db.commit()
        return cursor.rowcount == 1

    async def stale_drafts(self, created_before: datetime) -> list[str]:
        """Ids of conversations without any message created before the given time."""
        async with self._db.execute(
            "SELECT id FROM conversations c WHERE c.created_at < ? AND NOT EXISTS ("
            " SELECT 1 FROM messages m WHERE m.conversation_id = c.id)",
            # Stored as UTC ISO text: compare in the same zone and format.
            (created_before.astimezone(UTC).isoformat(timespec="microseconds"),),
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]

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

    async def get_message(self, message_id: int) -> StoredMessage | None:
        async with self._db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)) as cur:
            row = await cur.fetchone()
        return _message(row) if row else None

    async def previous_user_message(
        self, conversation_id: str, before_id: int
    ) -> StoredMessage | None:
        async with self._db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? AND role = 'user' AND id < ?"
            " ORDER BY id DESC LIMIT 1",
            (conversation_id, before_id),
        ) as cursor:
            row = await cursor.fetchone()
        return _message(row) if row else None

    async def add_message(
        self,
        conversation_id: str,
        role: Role,
        content: str,
        status: MessageStatus,
        generation: Generation | None = None,
    ) -> StoredMessage:
        now = _now()
        gen = generation
        cursor = await self._db.execute(
            "INSERT INTO messages (conversation_id, role, content, status, created_at,"
            " model, provider, base_prompt_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                role,
                content,
                status,
                now,
                gen.model if gen else None,
                gen.provider if gen else None,
                gen.base_prompt_version if gen else None,
            ),
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
            generation=generation,
        )

    async def delete_message(self, conversation_id: str, message_id: int) -> None:
        await self._db.execute(
            "DELETE FROM messages WHERE id = ? AND conversation_id = ?",
            (message_id, conversation_id),
        )
        await self._db.commit()
