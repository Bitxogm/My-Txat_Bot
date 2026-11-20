from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.domain.chat import Role
from app.domain.personality import GenerationParams

MessageStatus = Literal["done", "stopped", "error"]

TITLE_MAX_CHARS = 80


@dataclass(frozen=True, slots=True)
class PersonalitySnapshot:
    """The personality a conversation was created with, frozen at that moment (ADR-013).

    Editing or deleting the personality later does not change it. `id` is None for
    conversations created before personalities existed, or if the personality was deleted.
    """

    id: str | None = None
    name: str | None = None
    icon: str | None = None
    system_prompt: str = ""
    params: GenerationParams = field(default_factory=GenerationParams)


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    title: str
    model: str
    created_at: datetime
    updated_at: datetime
    personality: PersonalitySnapshot = field(default_factory=PersonalitySnapshot)


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: int
    conversation_id: str
    role: Role
    content: str
    status: MessageStatus
    created_at: datetime


def title_from_message(content: str) -> str:
    """First line of the first user message, trimmed to a sidebar-friendly length."""
    first_line = " ".join(content.strip().split("\n", 1)[0].split())
    if len(first_line) <= TITLE_MAX_CHARS:
        return first_line or "Nueva conversación"
    return first_line[: TITLE_MAX_CHARS - 1].rstrip() + "…"
