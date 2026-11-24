from typing import Protocol

from app.domain.feedback import Feedback, FeedbackFilter, FeedbackReason, Rating, TurnCopy


class FeedbackRepository(Protocol):
    async def upsert(
        self,
        message_id: int,
        conversation_id: str,
        rating: Rating,
        reasons: tuple[FeedbackReason, ...],
        correction: str | None,
        turn: TurnCopy,
    ) -> Feedback:
        """Create the rating of a reply or replace it (one per reply). Keeps `created_at`."""
        ...

    async def get_by_message(self, message_id: int) -> Feedback | None: ...

    async def for_conversation(self, conversation_id: str) -> dict[int, Feedback]:
        """Ratings of a conversation's replies, by message id."""
        ...

    async def delete_by_message(self, message_id: int) -> bool: ...

    async def search(
        self, filters: FeedbackFilter, limit: int, offset: int
    ) -> tuple[list[Feedback], int]:
        """Newest first, and the total matching the filters."""
        ...

    async def export(self, filters: FeedbackFilter) -> list[Feedback]:
        """Every rating matching the filters, oldest first."""
        ...
