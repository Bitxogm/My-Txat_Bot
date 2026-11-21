"""Fitting a conversation into the model's context window.

A model can only read `num_ctx` tokens: the system prompt, the history, the new message and the
reply it writes. Instead of letting the request fail (or the reply get cut), the history is
shaped to fit before it is sent: the newest turns are kept, older ones lose first their images,
then their files' contents, and the oldest are dropped. The model is told when that happened.

Token counts are estimates (no tokenizer for every model): text at 3 characters per token,
which overestimates Spanish prose and is close for code and Markdown; images from their size.
"""

import math
import struct
from dataclasses import dataclass, field

from app.core.errors import ContextTooLongError
from app.domain.attachment import (
    ATTACHMENT_PROMPT_MAX_CHARS,
    Attachment,
    format_attachments_for_model,
)
from app.domain.chat import ChatMessage, ImageData, Role

CHARS_PER_TOKEN = 3
MESSAGE_OVERHEAD_TOKENS = 8
# Vision models cut images into 28x28 px tiles, one token each (Qwen-VL family; others use
# fewer). Images are stored at most 1568 px per side, so at most 56 x 56 tiles.
IMAGE_TILE_PX = 28
IMAGE_FALLBACK_TOKENS = 3200
# Room left for the reply: Ollama counts it inside the same window.
REPLY_RESERVE_TOKENS = 2048
# Files of the new message get at least this many characters each, or it doesn't fit.
MIN_FILE_CHARS = 1000

DROPPED_NOTE = (
    "[Nota del sistema: los {count} mensajes más antiguos de esta conversación no caben en el"
    " contexto del modelo y se han omitido.]"
)


def text_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def image_size(data: bytes) -> tuple[int, int] | None:
    """Width and height of a PNG or JPEG, read from its header. Only for images the server
    re-encoded itself (adapters/files/images.py); anything else gives None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return width, height
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                return None
            marker = data[i + 1]
            length = struct.unpack(">H", data[i + 2 : i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                height, width = struct.unpack(">HH", data[i + 5 : i + 9])
                return width, height
            i += 2 + length
    return None


def image_tokens(image: ImageData) -> int:
    size = image_size(image.data)
    if size is None:
        return IMAGE_FALLBACK_TOKENS
    width, height = size
    return math.ceil(width / IMAGE_TILE_PX) * math.ceil(height / IMAGE_TILE_PX)


def message_tokens(message: ChatMessage) -> int:
    return (
        MESSAGE_OVERHEAD_TOKENS
        + text_tokens(message.content)
        + sum(image_tokens(image) for image in message.images)
    )


def reply_reserve(budget: int) -> int:
    return min(REPLY_RESERVE_TOKENS, budget // 4)


@dataclass(frozen=True, slots=True)
class Turn:
    """A message of the conversation before formatting. `images` are the ones that may be sent
    (already loaded; empty for a model without vision)."""

    role: Role
    text: str
    files: list[Attachment] = field(default_factory=list)
    images: tuple[ImageData, ...] = ()


@dataclass(frozen=True, slots=True)
class FittedHistory:
    messages: list[ChatMessage]
    dropped_turns: int
    dropped_images: int
    omitted_files: int


def _variants(turn: Turn) -> list[tuple[ChatMessage, int, int]]:
    """Ways to send an earlier turn, richest first, with the images and files each one drops."""
    if turn.role != "user":
        return [(ChatMessage(role=turn.role, content=turn.text), 0, 0)]
    text_files = sum(1 for f in turn.files if f.kind != "image")
    full = format_attachments_for_model(turn.files, turn.text)
    options = [(ChatMessage(role="user", content=full, images=turn.images), 0, 0)]
    if turn.images:
        options.append((ChatMessage(role="user", content=full), len(turn.images), 0))
    if text_files:
        stub = format_attachments_for_model(turn.files, turn.text, max_chars_per_file=0)
        options.append((ChatMessage(role="user", content=stub), len(turn.images), text_files))
    return options


def _current_message(turn: Turn, room: int) -> ChatMessage:
    """The new message, with its files cut so the whole message fits in `room` tokens."""
    fixed = MESSAGE_OVERHEAD_TOKENS + sum(image_tokens(i) for i in turn.images)
    plain = ChatMessage(role="user", content=format_attachments_for_model(turn.files, turn.text, 0))
    if fixed + text_tokens(plain.content) > room:
        raise ContextTooLongError
    text_files = sum(1 for f in turn.files if f.kind != "image")
    if not text_files:
        return ChatMessage(role="user", content=plain.content, images=turn.images)
    spare_chars = (room - fixed - text_tokens(plain.content)) * CHARS_PER_TOKEN
    per_file = min(ATTACHMENT_PROMPT_MAX_CHARS, spare_chars // text_files - 200)
    if per_file < MIN_FILE_CHARS:
        raise ContextTooLongError
    content = format_attachments_for_model(turn.files, turn.text, per_file)
    return ChatMessage(role="user", content=content, images=turn.images)


def fit_history(
    system_prompt: str, earlier: list[Turn], current: Turn, budget: int
) -> FittedHistory:
    """The messages to send: system prompt, as much history as fits (newest first) and the new
    message. Raises ContextTooLongError when not even the new message fits."""
    system = ChatMessage(role="system", content=system_prompt)
    room = budget - reply_reserve(budget) - message_tokens(system)
    # The note about dropped turns may be added later; keep room for it.
    room -= text_tokens(DROPPED_NOTE.format(count=9999)) + MESSAGE_OVERHEAD_TOKENS
    newest = _current_message(current, room)
    room -= message_tokens(newest)

    kept: list[ChatMessage] = []
    dropped_images = omitted_files = 0
    for turn in reversed(earlier):
        for message, images_lost, files_lost in _variants(turn):
            cost = message_tokens(message)
            if cost <= room:
                kept.append(message)
                room -= cost
                dropped_images += images_lost
                omitted_files += files_lost
                break
        else:
            break  # this turn doesn't fit in any form: it and everything older are left out
    kept.reverse()
    # The history must open with the user's turn, not with a reply to a dropped question.
    while kept and kept[0].role != "user":
        kept.pop(0)
    dropped = len(earlier) - len(kept)

    messages = [system, *kept, newest]
    if dropped:
        first = messages[1]
        note = DROPPED_NOTE.format(count=dropped)
        messages[1] = ChatMessage(
            role=first.role, content=f"{note}\n\n{first.content}", images=first.images
        )
    return FittedHistory(
        messages=messages,
        dropped_turns=dropped,
        dropped_images=dropped_images,
        omitted_files=omitted_files,
    )
