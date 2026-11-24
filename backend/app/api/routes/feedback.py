"""Ratings of the assistant's replies (ADR-024): 👍/👎, reasons and a written correction."""

import json
import unicodedata
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.dependencies import (
    get_app_settings,
    get_attachment_repository,
    get_conversation_repository,
    get_feedback_repository,
)
from app.core.config import Settings
from app.core.errors import (
    FeedbackNotAllowedError,
    FeedbackNotFoundError,
    MessageNotFoundError,
)
from app.domain.feedback import (
    FEEDBACK_REASONS,
    MAX_CORRECTION_CHARS,
    RATEABLE_STATUSES,
    Feedback,
    FeedbackFilter,
    FeedbackReason,
    Rating,
    TurnCopy,
)
from app.ports.attachments import AttachmentRepository
from app.ports.conversations import ConversationRepository
from app.ports.feedback import FeedbackRepository

router = APIRouter(tags=["feedback"])

Repo = Annotated[FeedbackRepository, Depends(get_feedback_repository)]
MessageId = Annotated[int, Path(ge=1, le=2**63 - 1)]

# Invisible and control characters (bidi overrides, zero-width, line separators, private use...)
# could hide or reorder text in a correction that will end up in the RAG or a training set.
# Same rule as file names (domain/attachment.py), but tabs and newlines are allowed.
_UNSAFE = frozenset({"Cc", "Cf", "Zl", "Zp", "Co", "Cs", "Cn"})
_ALLOWED_CONTROL = frozenset("\t\n\r")
# JSON allows these raw inside strings, but line-based readers split on them.
_LINE_BREAKS = {"\u2028": "\\u2028", "\u2029": "\\u2029", "\x85": "\\u0085"}


class FeedbackIn(BaseModel):
    """PUT replaces the whole rating. 👍 carries no reasons or correction."""

    model_config = ConfigDict(extra="forbid")

    rating: Rating
    reasons: list[FeedbackReason] = Field(default_factory=list, max_length=len(FEEDBACK_REASONS))
    correction: str | None = Field(default=None, max_length=MAX_CORRECTION_CHARS)

    @field_validator("rating", mode="before")
    @classmethod
    def _integer(cls, rating: object) -> object:
        # Without this, lax mode turns true and 1.0 into 1.
        if isinstance(rating, bool) or not isinstance(rating, int):
            raise ValueError("rating debe ser 1 o -1")
        return rating

    @field_validator("reasons")
    @classmethod
    def _unique(cls, reasons: list[FeedbackReason]) -> list[FeedbackReason]:
        if len(set(reasons)) != len(reasons):
            raise ValueError("Motivos repetidos")
        return reasons

    @field_validator("correction")
    @classmethod
    def _clean(cls, correction: str | None) -> str | None:
        if correction is None:
            return None
        if any(
            unicodedata.category(ch) in _UNSAFE and ch not in _ALLOWED_CONTROL for ch in correction
        ):
            raise ValueError("La corrección contiene caracteres no válidos")
        return correction.strip() or None

    @model_validator(mode="after")
    def _only_for_thumbs_down(self) -> "FeedbackIn":
        if self.rating == 1 and (self.reasons or self.correction):
            raise ValueError("Los motivos y la corrección son solo para 👎")
        return self


class FeedbackOut(BaseModel):
    message_id: int
    conversation_id: str
    rating: Rating
    reasons: list[FeedbackReason]
    correction: str | None
    question: str
    question_files: list[str]
    answer: str
    model: str
    model_approximate: bool
    provider: str | None
    personality: str | None
    # null = unknown (replies saved before it was recorded).
    base_prompt_version: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, f: Feedback) -> "FeedbackOut":
        turn = f.turn
        return cls(
            message_id=f.message_id,
            conversation_id=f.conversation_id,
            rating=f.rating,
            reasons=list(f.reasons),
            correction=f.correction,
            question=turn.question,
            question_files=list(turn.question_files),
            answer=turn.answer,
            model=turn.model,
            model_approximate=turn.model_approximate,
            provider=turn.provider,
            personality=turn.personality_name,
            base_prompt_version=turn.base_prompt_version,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )


class FeedbackPage(BaseModel):
    items: list[FeedbackOut]
    total: int


def _rating(value: int | None) -> int | None:
    if value is not None and value not in (1, -1):
        raise ValueError("rating debe ser 1 o -1")
    return value


def feedback_filter(
    rating: Annotated[int | None, Query(), AfterValidator(_rating)] = None,
    model: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    personality: Annotated[str | None, Query(min_length=1, max_length=60)] = None,
    reason: FeedbackReason | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    conversation_id: Annotated[str | None, Query(pattern=r"^[0-9a-f]{32}$")] = None,
) -> FeedbackFilter:
    return FeedbackFilter(
        rating=rating,  # type: ignore[arg-type]  # checked by _rating
        model=model,
        personality=personality,
        reason=reason,
        date_from=date_from,
        date_to=date_to,
        conversation_id=conversation_id,
    )


Filters = Annotated[FeedbackFilter, Depends(feedback_filter)]


async def _turn_copy(
    message_id: int,
    conversations: ConversationRepository,
    attachments: AttachmentRepository,
    settings: Settings,
) -> tuple[str, TurnCopy]:
    """The conversation id and a copy of the rated turn, as it is now."""
    message = await conversations.get_message(message_id)
    if message is None:
        raise MessageNotFoundError
    if message.role != "assistant":
        raise FeedbackNotAllowedError
    if message.status not in RATEABLE_STATUSES or not message.content.strip():
        raise FeedbackNotAllowedError("No se puede valorar una respuesta fallida o vacía")
    conversation = await conversations.get(message.conversation_id)
    if conversation is None:  # pragma: no cover - the foreign key keeps them together
        raise MessageNotFoundError
    question = await conversations.previous_user_message(conversation.id, message.id)
    files: list[str] = []
    if question is not None:
        files = [
            a.filename
            for a in await attachments.list_for_conversation(conversation.id)
            if a.message_id == question.id
        ]
    generation = message.generation
    if generation is not None:
        model, approximate = generation.model, False
        provider: str | None = generation.provider
        base_version: str | None = generation.base_prompt_version or None
    else:
        # Older replies: the conversation's last model, which may not be this reply's, and an
        # unknown base layer (the current one could differ from the one that wrote it).
        model, approximate, base_version = conversation.model, True, None
        configured = settings.provider_for(model)
        provider = configured.name if configured else "ollama"
    snap = conversation.personality
    return conversation.id, TurnCopy(
        question=question.content if question else "",
        question_files=tuple(files),
        answer=message.content,
        model=model,
        model_approximate=approximate,
        provider=provider,
        personality_id=snap.id,
        personality_name=snap.name,
        base_prompt_version=base_version,
    )


@router.put("/messages/{message_id}/feedback")
async def rate_message(
    message_id: MessageId,
    body: FeedbackIn,
    repo: Repo,
    conversations: Annotated[ConversationRepository, Depends(get_conversation_repository)],
    attachments: Annotated[AttachmentRepository, Depends(get_attachment_repository)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> FeedbackOut:
    """Create or replace the rating of an assistant reply (one per reply)."""
    conversation_id, turn = await _turn_copy(message_id, conversations, attachments, settings)
    saved = await repo.upsert(
        message_id,
        conversation_id,
        body.rating,
        tuple(body.reasons),
        body.correction,
        turn,
    )
    return FeedbackOut.of(saved)


@router.delete("/messages/{message_id}/feedback", status_code=204)
async def unrate_message(message_id: MessageId, repo: Repo) -> None:
    if not await repo.delete_by_message(message_id):
        raise FeedbackNotFoundError


@router.get("/feedback")
async def list_feedback(
    repo: Repo,
    filters: Filters,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> FeedbackPage:
    items, total = await repo.search(filters, limit, offset)
    return FeedbackPage(items=[FeedbackOut.of(f) for f in items], total=total)


def export_line(f: Feedback) -> str:
    """One JSONL line (docs/feedback-export.md): only the rating and its copy of the turn."""
    turn = f.turn
    line = json.dumps(
        {
            "question": turn.question,
            "question_files": list(turn.question_files),
            "answer": turn.answer,
            "rating": f.rating,
            "reasons": list(f.reasons),
            "correction": f.correction,
            "model": turn.model,
            "model_approximate": turn.model_approximate,
            "provider": turn.provider,
            "personality": turn.personality_name,
            "base_prompt_version": turn.base_prompt_version,
            "created_at": f.created_at.isoformat(),
            "updated_at": f.updated_at.isoformat(),
        },
        ensure_ascii=False,
    )
    for raw, escaped in _LINE_BREAKS.items():
        line = line.replace(raw, escaped)
    return line


@router.get(
    "/feedback/export",
    response_class=Response,
    responses={200: {"content": {"application/x-ndjson": {}}}},
)
async def export_feedback(repo: Repo, filters: Filters) -> Response:
    """Every matching rating as JSONL, oldest first, as a file download."""
    lines = [export_line(f) for f in await repo.export(filters)]
    body = "".join(f"{line}\n" for line in lines)
    filename = f"txat-feedback-{datetime.now(UTC).date().isoformat()}.jsonl"
    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
