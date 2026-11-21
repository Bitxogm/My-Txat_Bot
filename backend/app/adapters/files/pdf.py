import asyncio
import io
import logging
import multiprocessing
from multiprocessing.connection import Connection

from app.core.errors import UnreadableFileError

logger = logging.getLogger(__name__)

# Address space of the extraction process: a PDF bomb fails there instead of taking the backend.
PDF_PROCESS_MEMORY_BYTES = 1024 * 1024 * 1024

_ENCRYPTED = "encrypted"
_BROKEN = "broken"
_MESSAGES = {
    _ENCRYPTED: "El PDF está cifrado o protegido con contraseña",
    _BROKEN: "El PDF está dañado o no se puede leer",
}

# One extraction at a time: each one is a whole process, and a hostile PDF can use a full core.
_slot = asyncio.Semaphore(1)


def _extract(data: bytes, max_pages: int, max_chars: int) -> tuple[str, bool] | str:
    """Runs in the child. Returns (text, truncated) or an error code; never raises."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            return _ENCRYPTED
        pages = reader.pages
        truncated = len(pages) > max_pages
        parts: list[str] = []
        size = 0
        for page in pages[:max_pages]:
            text = page.extract_text() or ""
            parts.append(text)
            size += len(text)
            if size >= max_chars:
                truncated = True
                break
    except Exception:
        return _BROKEN
    text = "\n\n".join(p.strip() for p in parts if p.strip())
    if len(text) > max_chars:
        text, truncated = text[:max_chars], True
    return text, truncated


def _child(conn: Connection, data: bytes, max_pages: int, max_chars: int) -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (PDF_PROCESS_MEMORY_BYTES, PDF_PROCESS_MEMORY_BYTES))
    except (ImportError, ValueError, OSError):
        pass
    try:
        conn.send(_extract(data, max_pages, max_chars))
    except MemoryError:
        conn.send(_BROKEN)
    finally:
        conn.close()


def _run(data: bytes, max_pages: int, max_chars: int, timeout: float) -> tuple[str, bool] | str:
    """Blocking: runs the extraction in a child process and kills it on timeout."""
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(sender, data, max_pages, max_chars), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout):
            return "timeout"
        try:
            return receiver.recv()  # type: ignore[no-any-return]
        except EOFError:  # the child died (memory limit, crash)
            return _BROKEN
    finally:
        receiver.close()
        if process.is_alive():
            process.kill()
        process.join(timeout=5)


async def extract_pdf_text(
    data: bytes, max_pages: int, max_chars: int, time_limit: float
) -> tuple[str, bool]:
    """Text of the first `max_pages` pages, cut at `max_chars`. Returns (text, truncated).

    pypdf runs on untrusted input in a separate process with a memory cap, killed after
    `time_limit` seconds (a thread can't be stopped). Encrypted, malformed or text-less PDFs and
    timeouts raise UnreadableFileError.
    """
    async with _slot:
        result = await asyncio.to_thread(_run, data, max_pages, max_chars, time_limit)
    if result == "timeout":
        logger.warning("PDF text extraction timed out")
        raise UnreadableFileError("El PDF tarda demasiado en procesarse")
    if isinstance(result, str):
        logger.warning("Unreadable PDF: %s", result)
        raise UnreadableFileError(_MESSAGES.get(result, _MESSAGES[_BROKEN]))
    text, truncated = result
    if not text:
        raise UnreadableFileError(
            "El PDF no tiene texto extraíble (puede ser un escaneo); las imágenes llegarán más"
            " adelante"
        )
    return text, truncated
