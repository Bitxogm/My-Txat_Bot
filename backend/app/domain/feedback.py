"""Ratings of the assistant's replies (ADR-024).

A rating keeps a copy of the turn (question, reply, model, personality, base layer) taken when it
is saved, so the exported dataset doesn't depend on later changes. The model never sees ratings
yet: they are meant for the RAG (phase 4), the evaluation battery and, later, fine-tuning.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, get_args

Rating = Literal[1, -1]
FeedbackReason = Literal[
    "incorrect", "wrong_command", "incomplete", "too_long", "off_personality", "other"
]
FEEDBACK_REASONS: tuple[FeedbackReason, ...] = get_args(FeedbackReason)

MAX_CORRECTION_CHARS = 4000
# Replies that can be rated: finished or stopped by the user. Failed or empty ones can't.
RATEABLE_STATUSES = frozenset({"done", "stopped"})


@dataclass(frozen=True, slots=True)
class TurnCopy:
    """The rated turn as it was when rated."""

    question: str
    question_files: tuple[str, ...]
    answer: str
    model: str
    # True for replies saved before the model of each reply was recorded: the model is then
    # the conversation's last one, which may not be the one that wrote this reply.
    model_approximate: bool
    provider: str | None
    personality_id: str | None
    personality_name: str | None
    # None when unknown (replies saved before it was recorded).
    base_prompt_version: str | None


@dataclass(frozen=True, slots=True)
class Feedback:
    id: str
    message_id: int
    conversation_id: str
    rating: Rating
    reasons: tuple[FeedbackReason, ...]
    correction: str | None
    turn: TurnCopy
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FeedbackFilter:
    rating: Rating | None = None
    model: str | None = None
    personality: str | None = None
    reason: FeedbackReason | None = None
    date_from: date | None = None
    date_to: date | None = None
    conversation_id: str | None = None
