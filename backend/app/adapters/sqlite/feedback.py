import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast

import aiosqlite

from app.domain.feedback import Feedback, FeedbackFilter, FeedbackReason, Rating, TurnCopy


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _feedback(row: aiosqlite.Row) -> Feedback:
    return Feedback(
        id=row["id"],
        message_id=row["message_id"],
        conversation_id=row["conversation_id"],
        rating=cast(Rating, row["rating"]),
        reasons=tuple(cast(list[FeedbackReason], json.loads(row["reasons"]))),
        correction=row["correction"],
        turn=TurnCopy(
            question=row["question"],
            question_files=tuple(json.loads(row["question_files"])),
            answer=row["answer"],
            model=row["model"],
            model_approximate=bool(row["model_approximate"]),
            provider=row["provider"],
            personality_id=row["personality_id"],
            personality_name=row["personality_name"],
            base_prompt_version=row["base_prompt_version"],
        ),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _utc_start(day: date) -> str:
    """Midnight UTC of a date, in the stored ISO format."""
    return datetime.combine(day, time(), tzinfo=UTC).isoformat(timespec="microseconds")


def _where(filters: FeedbackFilter) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.rating is not None:
        clauses.append("rating = ?")
        params.append(filters.rating)
    if filters.model is not None:
        clauses.append("model = ?")
        params.append(filters.model)
    if filters.personality is not None:
        clauses.append("personality_name = ?")
        params.append(filters.personality)
    if filters.reason is not None:
        clauses.append("EXISTS (SELECT 1 FROM json_each(reasons) WHERE value = ?)")
        params.append(filters.reason)
    if filters.date_from is not None:
        clauses.append("created_at >= ?")
        params.append(_utc_start(filters.date_from))
    if filters.date_to is not None:  # inclusive: the whole last day
        clauses.append("created_at < ?")
        params.append(_utc_start(filters.date_to + timedelta(days=1)))
    if filters.conversation_id is not None:
        clauses.append("conversation_id = ?")
        params.append(filters.conversation_id)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


class SqliteFeedbackRepository:
    """FeedbackRepository on the shared aiosqlite connection."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(
        self,
        message_id: int,
        conversation_id: str,
        rating: Rating,
        reasons: tuple[FeedbackReason, ...],
        correction: str | None,
        turn: TurnCopy,
    ) -> Feedback:
        now = _now()
        await self._db.execute(
            "INSERT INTO message_feedback (id, message_id, conversation_id, rating, reasons,"
            " correction, question, question_files, answer, model, model_approximate, provider,"
            " personality_id, personality_name, base_prompt_version, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (message_id) DO UPDATE SET rating = excluded.rating,"
            " reasons = excluded.reasons, correction = excluded.correction,"
            " question = excluded.question, question_files = excluded.question_files,"
            " answer = excluded.answer, model = excluded.model,"
            " model_approximate = excluded.model_approximate, provider = excluded.provider,"
            " personality_id = excluded.personality_id,"
            " personality_name = excluded.personality_name,"
            " base_prompt_version = excluded.base_prompt_version,"
            " updated_at = excluded.updated_at",
            (
                uuid.uuid4().hex,
                message_id,
                conversation_id,
                rating,
                json.dumps(list(reasons)),
                correction,
                turn.question,
                json.dumps(list(turn.question_files), ensure_ascii=False),
                turn.answer,
                turn.model,
                int(turn.model_approximate),
                turn.provider,
                turn.personality_id,
                turn.personality_name,
                turn.base_prompt_version,
                now,
                now,
            ),
        )
        await self._db.commit()
        saved = await self.get_by_message(message_id)
        if saved is None:  # pragma: no cover - just written
            raise RuntimeError("feedback vanished after insert")
        return saved

    async def get_by_message(self, message_id: int) -> Feedback | None:
        async with self._db.execute(
            "SELECT * FROM message_feedback WHERE message_id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _feedback(row) if row else None

    async def for_conversation(self, conversation_id: str) -> dict[int, Feedback]:
        async with self._db.execute(
            "SELECT * FROM message_feedback WHERE conversation_id = ?", (conversation_id,)
        ) as cursor:
            return {row["message_id"]: _feedback(row) for row in await cursor.fetchall()}

    async def delete_by_message(self, message_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM message_feedback WHERE message_id = ?", (message_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def search(
        self, filters: FeedbackFilter, limit: int, offset: int
    ) -> tuple[list[Feedback], int]:
        where, params = _where(filters)
        async with self._db.execute(
            f"SELECT COUNT(*) FROM message_feedback{where}",  # noqa: S608 - fixed fragments, values bound
            params,
        ) as cursor:
            row = await cursor.fetchone()
        total = int(row[0]) if row else 0
        async with self._db.execute(
            f"SELECT * FROM message_feedback{where}"  # noqa: S608 - fixed fragments, values bound
            " ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ) as cursor:
            return [_feedback(r) for r in await cursor.fetchall()], total

    async def export(self, filters: FeedbackFilter) -> list[Feedback]:
        where, params = _where(filters)
        async with self._db.execute(
            f"SELECT * FROM message_feedback{where}"  # noqa: S608 - fixed fragments, values bound
            " ORDER BY created_at, id",
            params,
        ) as cursor:
            return [_feedback(r) for r in await cursor.fetchall()]
