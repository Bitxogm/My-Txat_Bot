import io
import logging

from app.adapters.files.isolated import TIMEOUT, run_isolated
from app.core.errors import UnreadableFileError

logger = logging.getLogger(__name__)

_ENCRYPTED = "encrypted"
_BROKEN = "broken"
_MESSAGES = {
    _ENCRYPTED: "El PDF está cifrado o protegido con contraseña",
    _BROKEN: "El PDF está dañado o no se puede leer",
}


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
    except Exception:  # any failure on untrusted input (also RecursionError)
        return _BROKEN
    text = "\n\n".join(p.strip() for p in parts if p.strip())
    if len(text) > max_chars:
        text, truncated = text[:max_chars], True
    return text, truncated


async def extract_pdf_text(
    data: bytes, max_pages: int, max_chars: int, time_limit: float
) -> tuple[str, bool]:
    """Text of the first `max_pages` pages, cut at `max_chars`. Returns (text, truncated).

    pypdf runs on untrusted input in a killable child process (adapters/files/isolated.py).
    Encrypted, malformed or text-less PDFs and timeouts raise UnreadableFileError.
    """
    result = await run_isolated(_extract, data, max_pages, max_chars, time_limit=time_limit)
    if result == TIMEOUT:
        logger.warning("PDF text extraction timed out")
        raise UnreadableFileError("El PDF tarda demasiado en procesarse")
    if isinstance(result, str):
        logger.warning("Unreadable PDF: %s", result)
        raise UnreadableFileError(_MESSAGES.get(result, _MESSAGES[_BROKEN]))
    text, truncated = result
    if not text:
        raise UnreadableFileError(
            "El PDF no tiene texto extraíble (puede ser un escaneo): conviértelo a imagen y"
            " adjúntalo con un modelo con visión"
        )
    return text, truncated
