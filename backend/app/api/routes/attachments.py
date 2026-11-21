import asyncio
import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from app.adapters.files.images import normalize_image
from app.adapters.files.pdf import extract_pdf_text
from app.api.dependencies import (
    get_app_settings,
    get_attachment_repository,
    get_conversation_repository,
    get_file_storage,
)
from app.core.config import Settings
from app.core.errors import (
    AttachmentNotFoundError,
    BadRequestError,
    ConversationNotFoundError,
    LengthRequiredError,
    PayloadTooLargeError,
    UnreadableFileError,
)
from app.domain.attachment import (
    ATTACHMENT_STORED_MAX_CHARS,
    IMAGE_MAX_PIXELS,
    IMAGE_MAX_SIDE,
    IMAGE_NORMALIZE_TIMEOUT_SECONDS,
    MAX_ATTACHMENTS_PER_MESSAGE,
    PDF_EXTRACT_TIMEOUT_SECONDS,
    PDF_MAX_PAGES,
    Attachment,
    AttachmentKind,
    clean_text,
    clip,
    decode_text,
    detect_kind,
    sanitize_filename,
)
from app.ports.attachments import AttachmentRepository
from app.ports.conversations import ConversationRepository
from app.ports.file_storage import FileStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations/{conversation_id}/attachments", tags=["attachments"])

ConversationId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
AttachmentId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
Repo = Annotated[AttachmentRepository, Depends(get_attachment_repository)]
Conversations = Annotated[ConversationRepository, Depends(get_conversation_repository)]
Storage = Annotated[FileStorage, Depends(get_file_storage)]

# Room for the multipart boundaries and headers around the file itself.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
_CHUNK = 1024 * 1024


class AttachmentOut(BaseModel):
    """Metadata only: the stored bytes, their path and the extracted text never leave the server
    through this API."""

    id: str
    filename: str
    mime: str
    kind: AttachmentKind
    size_bytes: int
    truncated: bool
    sent: bool
    created_at: datetime

    @classmethod
    def of(cls, a: Attachment) -> "AttachmentOut":
        return cls(
            id=a.id,
            filename=a.filename,
            mime=a.mime,
            kind=a.kind,
            size_bytes=a.size_bytes,
            truncated=a.truncated,
            sent=a.message_id is not None,
            created_at=a.created_at,
        )


class AttachmentList(BaseModel):
    attachments: list[AttachmentOut]


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(_CHUNK):
        size += len(chunk)
        if size > limit:
            raise PayloadTooLargeError(
                f"El fichero supera el máximo de {limit // (1024 * 1024)} MB"
            )
        chunks.append(chunk)
    if size == 0:
        raise UnreadableFileError("El fichero está vacío")
    return b"".join(chunks)


def _text_of(filename: str, data: bytes) -> tuple[AttachmentKind, str, str, bool]:
    """Blocking (decoding up to UPLOAD_MAX_MB of text): run it off the event loop."""
    kind, mime = detect_kind(filename, data)
    if kind != "text":
        return kind, mime, "", False
    text, truncated = clip(decode_text(data), ATTACHMENT_STORED_MAX_CHARS)
    return kind, mime, text, truncated


class _Inspected(BaseModel):
    kind: AttachmentKind
    mime: str
    text: str
    truncated: bool
    # What is stored: the upload itself, or the re-encoded image.
    stored: bytes


async def _inspect(filename: str, data: bytes) -> _Inspected:
    kind, mime, text, truncated = await asyncio.to_thread(_text_of, filename, data)
    stored = data
    if kind == "pdf":
        raw, truncated = await extract_pdf_text(
            data, PDF_MAX_PAGES, ATTACHMENT_STORED_MAX_CHARS, PDF_EXTRACT_TIMEOUT_SECONDS
        )
        text = clean_text(raw)
        if not text.strip():
            raise UnreadableFileError("El PDF no tiene texto extraíble")
    elif kind == "image":
        # Never store or forward the upload as is: decoded and re-encoded without metadata.
        stored, mime = await normalize_image(
            data, mime, IMAGE_MAX_PIXELS, IMAGE_MAX_SIDE, IMAGE_NORMALIZE_TIMEOUT_SECONDS
        )
    return _Inspected(kind=kind, mime=mime, text=text, truncated=truncated, stored=stored)


def _too_many() -> BadRequestError:
    return BadRequestError(
        f"Como máximo {MAX_ATTACHMENTS_PER_MESSAGE} ficheros por mensaje. Envía o quita alguno."
    )


@router.post("", status_code=201)
async def upload_attachment(
    conversation_id: ConversationId,
    request: Request,
    repo: Repo,
    conversations: Conversations,
    storage: Storage,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AttachmentOut:
    """multipart/form-data with one `file` field. The file is validated by its content, stored
    under a server-generated name and its text extracted."""
    if await conversations.get(conversation_id) is None:
        raise ConversationNotFoundError
    limit = settings.upload_max_bytes
    # Starlette spools the whole multipart body to disk before the handler can count it, so the
    # size must be known up front: no Content-Length (chunked) is refused. The server never
    # reads past the declared length.
    declared = request.headers.get("content-length", "")
    if not declared.isdigit():
        raise LengthRequiredError
    if int(declared) > limit + MULTIPART_OVERHEAD_BYTES:
        raise PayloadTooLargeError(f"El fichero supera el máximo de {limit // (1024 * 1024)} MB")

    if await repo.count_unsent(conversation_id) >= MAX_ATTACHMENTS_PER_MESSAGE:
        raise _too_many()

    try:
        form = await request.form(max_files=1, max_fields=1)
    except MultiPartException as exc:
        raise BadRequestError("Formulario de subida no válido") from exc
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise BadRequestError("Falta el fichero (campo «file»)")
        filename = sanitize_filename(upload.filename)
        data = await _read_limited(upload, limit)
    finally:
        await form.close()

    inspected = await _inspect(filename, data)
    key = await storage.save(inspected.stored)
    attachment = Attachment(
        id=uuid.uuid4().hex,
        conversation_id=conversation_id,
        message_id=None,
        filename=filename,
        mime=inspected.mime,
        kind=inspected.kind,
        size_bytes=len(inspected.stored),
        sha256=hashlib.sha256(inspected.stored).hexdigest(),
        storage_key=key,
        text=inspected.text,
        truncated=inspected.truncated,
        created_at=datetime.now(UTC),
    )
    try:
        # Atomic check of the pending limit: parallel uploads can't all slip past the count above.
        added = await repo.add_if_room(attachment, MAX_ATTACHMENTS_PER_MESSAGE)
    except BaseException:
        await storage.delete(key)  # no orphan files on disk
        raise
    if not added:
        await storage.delete(key)
        raise _too_many()
    logger.info("Attachment stored: kind=%s size=%d", inspected.kind, len(inspected.stored))
    return AttachmentOut.of(attachment)


@router.get("")
async def list_attachments(
    conversation_id: ConversationId, repo: Repo, conversations: Conversations
) -> AttachmentList:
    if await conversations.get(conversation_id) is None:
        raise ConversationNotFoundError
    attachments = await repo.list_for_conversation(conversation_id)
    return AttachmentList(attachments=[AttachmentOut.of(a) for a in attachments])


@router.delete("/{attachment_id}", status_code=204)
async def delete_attachment(
    conversation_id: ConversationId, attachment_id: AttachmentId, repo: Repo, storage: Storage
) -> None:
    """Only files not yet sent: a sent file is part of the conversation history."""
    deleted = await repo.delete_unsent(conversation_id, attachment_id)
    if deleted is None:
        raise AttachmentNotFoundError
    await storage.delete(deleted.storage_key)


# Only images are served back (thumbnails in the chat): bytes the server itself re-encoded, with
# a fixed type, never sniffed, never rendered as a document.
_IMAGE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Content-Disposition": "inline",
    # Revalidated on every use: after a logout or a deleted conversation the browser must not
    # keep showing it from its cache.
    "Cache-Control": "private, no-cache",
    "Cross-Origin-Resource-Policy": "same-origin",
}


@router.get("/{attachment_id}/content")
async def attachment_content(
    conversation_id: ConversationId, attachment_id: AttachmentId, repo: Repo, storage: Storage
) -> Response:
    attachment = await repo.get(conversation_id, attachment_id)
    if (
        attachment is None
        or attachment.kind != "image"
        or attachment.mime not in ("image/png", "image/jpeg")
    ):
        raise AttachmentNotFoundError
    try:
        data = await storage.read(attachment.storage_key)
    except FileNotFoundError as exc:
        raise AttachmentNotFoundError from exc
    return Response(content=data, media_type=attachment.mime, headers=_IMAGE_HEADERS)
