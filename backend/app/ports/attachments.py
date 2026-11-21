from typing import Protocol

from app.domain.attachment import Attachment


class AttachmentRepository(Protocol):
    async def add_if_room(self, attachment: Attachment, max_unsent: int) -> bool:
        """Insert it only while the conversation has fewer than `max_unsent` unsent ones
        (atomically). Returns whether it was inserted."""
        ...

    async def count_unsent(self, conversation_id: str) -> int: ...

    async def get(self, conversation_id: str, attachment_id: str) -> Attachment | None: ...

    async def list_for_conversation(self, conversation_id: str) -> list[Attachment]:
        """Oldest first."""
        ...

    async def attach_to_message(
        self, conversation_id: str, attachment_ids: list[str], message_id: int
    ) -> int:
        """Link unsent attachments of this conversation to a message. Returns how many."""
        ...

    async def release(self, message_id: int) -> None:
        """Unlink the attachments of a message again (undo of attach_to_message)."""
        ...

    async def delete_unsent(self, conversation_id: str, attachment_id: str) -> Attachment | None:
        """Delete an attachment not yet sent with a message; returns it (for its file)."""
        ...

    async def storage_keys(self, conversation_id: str | None = None) -> list[str]:
        """Keys of a conversation's files, or of all files with None."""
        ...
