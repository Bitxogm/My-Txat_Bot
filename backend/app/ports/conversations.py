from datetime import datetime
from typing import Protocol

from app.domain.chat import Role
from app.domain.conversation import (
    Conversation,
    MessageStatus,
    PersonalitySnapshot,
    StoredMessage,
)


class ConversationRepository(Protocol):
    async def create(
        self, title: str, model: str, personality: PersonalitySnapshot | None = None
    ) -> Conversation:
        """`personality` is stored as an immutable snapshot."""
        ...

    async def list_all(self) -> list[Conversation]:
        """Most recently updated first."""
        ...

    async def get(self, conversation_id: str) -> Conversation | None: ...

    async def update(
        self, conversation_id: str, *, title: str | None = None, model: str | None = None
    ) -> Conversation | None: ...

    async def delete(self, conversation_id: str) -> bool: ...

    async def set_personality_if_draft(
        self, conversation_id: str, personality: PersonalitySnapshot
    ) -> bool:
        """Change the personality while the conversation is a draft (no user message, ADR-022)."""
        ...

    async def stale_drafts(self, created_before: datetime) -> list[str]:
        """Drafts (no messages at all) created before the given time."""
        ...

    async def messages(self, conversation_id: str) -> list[StoredMessage]:
        """Oldest first."""
        ...

    async def add_message(
        self, conversation_id: str, role: Role, content: str, status: MessageStatus
    ) -> StoredMessage:
        """Append a message and bump the conversation's updated_at."""
        ...

    async def delete_message(self, conversation_id: str, message_id: int) -> None: ...
