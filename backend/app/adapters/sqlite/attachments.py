from datetime import datetime
from typing import cast

import aiosqlite

from app.domain.attachment import Attachment, AttachmentKind


def _attachment(row: aiosqlite.Row) -> Attachment:
    return Attachment(
        id=row["id"],
        conversation_id=row["conversation_id"],
        message_id=row["message_id"],
        filename=row["filename"],
        mime=row["mime"],
        kind=cast(AttachmentKind, row["kind"]),
        size_bytes=row["size_bytes"],
        sha256=row["sha256"],
        storage_key=row["storage_key"],
        text=row["text"],
        truncated=bool(row["truncated"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SqliteAttachmentRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def add_if_room(self, attachment: Attachment, max_unsent: int) -> bool:
        a = attachment
        cursor = await self._db.execute(
            "INSERT INTO attachments (id, conversation_id, message_id, filename, mime, kind,"
            " size_bytes, sha256, storage_key, text, truncated, created_at)"
            " SELECT ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?"
            " WHERE (SELECT COUNT(*) FROM attachments"
            " WHERE conversation_id = ? AND message_id IS NULL) < ?",
            (
                a.id,
                a.conversation_id,
                a.filename,
                a.mime,
                a.kind,
                a.size_bytes,
                a.sha256,
                a.storage_key,
                a.text,
                int(a.truncated),
                a.created_at.isoformat(timespec="microseconds"),
                a.conversation_id,
                max_unsent,
            ),
        )
        await self._db.commit()
        return cursor.rowcount == 1

    async def count_unsent(self, conversation_id: str) -> int:
        async with self._db.execute(
            "SELECT COUNT(*) FROM attachments WHERE conversation_id = ? AND message_id IS NULL",
            (conversation_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get(self, conversation_id: str, attachment_id: str) -> Attachment | None:
        async with self._db.execute(
            "SELECT * FROM attachments WHERE id = ? AND conversation_id = ?",
            (attachment_id, conversation_id),
        ) as cursor:
            row = await cursor.fetchone()
        return _attachment(row) if row else None

    async def list_for_conversation(self, conversation_id: str) -> list[Attachment]:
        async with self._db.execute(
            "SELECT * FROM attachments WHERE conversation_id = ? ORDER BY created_at, id",
            (conversation_id,),
        ) as cursor:
            return [_attachment(row) for row in await cursor.fetchall()]

    async def attach_to_message(
        self, conversation_id: str, attachment_ids: list[str], message_id: int
    ) -> int:
        if not attachment_ids:
            return 0
        placeholders = ", ".join("?" for _ in attachment_ids)
        cursor = await self._db.execute(
            f"UPDATE attachments SET message_id = ?"  # noqa: S608 - placeholders only
            f" WHERE conversation_id = ? AND message_id IS NULL AND id IN ({placeholders})",
            (message_id, conversation_id, *attachment_ids),
        )
        await self._db.commit()
        return cursor.rowcount

    async def release(self, message_id: int) -> None:
        await self._db.execute(
            "UPDATE attachments SET message_id = NULL WHERE message_id = ?", (message_id,)
        )
        await self._db.commit()

    async def delete_unsent(self, conversation_id: str, attachment_id: str) -> Attachment | None:
        attachment = await self.get(conversation_id, attachment_id)
        if attachment is None or attachment.message_id is not None:
            return None
        await self._db.execute(
            "DELETE FROM attachments WHERE id = ? AND message_id IS NULL", (attachment_id,)
        )
        await self._db.commit()
        return attachment

    async def storage_keys(self, conversation_id: str | None = None) -> list[str]:
        if conversation_id is None:
            query, params = "SELECT storage_key FROM attachments", ()
        else:
            query = "SELECT storage_key FROM attachments WHERE conversation_id = ?"
            params = (conversation_id,)
        async with self._db.execute(query, params) as cursor:
            return [row[0] for row in await cursor.fetchall()]
