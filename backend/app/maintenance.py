"""Housekeeping run at startup."""

import logging
from datetime import UTC, datetime, timedelta

from app.domain.conversation import DRAFT_MAX_AGE_HOURS
from app.ports.attachments import AttachmentRepository
from app.ports.conversations import ConversationRepository
from app.ports.file_storage import FileStorage

logger = logging.getLogger(__name__)


async def sweep_stale_drafts(
    conversations: ConversationRepository,
    attachments: AttachmentRepository,
    storage: FileStorage,
    now: datetime | None = None,
) -> int:
    """Delete drafts (conversations with no messages, ADR-022) older than DRAFT_MAX_AGE_HOURS,
    with their uploaded files. They are never listed, so nobody would find them again."""
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=DRAFT_MAX_AGE_HOURS)
    removed = 0
    for conversation_id in await conversations.stale_drafts(cutoff):
        keys = await attachments.storage_keys(conversation_id)
        if not await conversations.delete(conversation_id):
            continue
        removed += 1
        for key in keys:
            try:
                await storage.delete(key)
            except (OSError, ValueError) as exc:  # the orphan-file sweep retries next time
                logger.warning("Could not delete a draft's file: %s", type(exc).__name__)
    return removed
