from typing import Protocol

from app.domain.chat import Role
from app.domain.conversation import Conversation, MessageStatus, StoredMessage


class ConversationRepository(Protocol):
    async def create(self, title: str, model: str) -> Conversation: ...

    async def list_all(self) -> list[Conversation]:
        """Most recently updated first."""
        ...

    async def get(self, conversation_id: str) -> Conversation | None: ...

    async def update(
        self, conversation_id: str, *, title: str | None = None, model: str | None = None
    ) -> Conversation | None: ...

    async def delete(self, conversation_id: str) -> bool: ...

    async def messages(self, conversation_id: str) -> list[StoredMessage]:
        """Oldest first."""
        ...

    async def add_message(
        self, conversation_id: str, role: Role, content: str, status: MessageStatus
    ) -> StoredMessage:
        """Append a message and bump the conversation's updated_at."""
        ...
