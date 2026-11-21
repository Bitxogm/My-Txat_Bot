import io
import logging

from app.adapters.files.isolated import TIMEOUT, run_isolated
from app.core.errors import UnreadableFileError

logger = logging.getLogger(__name__)

_BROKEN = "broken"
_TOO_BIG = "too_big"

# Pillow format names per accepted MIME type. Image.open is limited to the one the magic number
# announced: otherwise, when that parser fails, Pillow tries every other decoder it has (TGA,
# PCD, SPIDER...), widening the attack surface to rarely audited C code.
_FORMATS: dict[str, tuple[str, ...]] = {
    "image/png": ("PNG",),
    "image/jpeg": ("JPEG", "MPO"),  # multi-picture JPEGs (phones) open as MPO
    "image/gif": ("GIF",),
    "image/webp": ("WEBP",),
}
# A lossless re-encode above this size (a noisy photo saved as PNG) is redone as JPEG.
_PNG_MAX_BYTES = 2 * 1024 * 1024


def _normalize(
    data: bytes, source_mime: str, max_pixels: int, max_side: int
) -> tuple[bytes, str] | str:
    """Runs in the child. Decodes the image, keeps the first frame and re-encodes it at most
    `max_side` px wide/tall into a NEW image, so no metadata survives (EXIF, GPS, ICC, comments,
    text chunks): PNG when it has transparency or came lossless, JPEG otherwise. Returns
    (bytes, mime) or an error code; never raises."""
    from PIL import Image

    formats = _FORMATS.get(source_mime)
    if formats is None:
        return _BROKEN
    try:
        Image.MAX_IMAGE_PIXELS = max_pixels  # larger images raise DecompressionBombError
        with Image.open(io.BytesIO(data), formats=formats) as probe:
            if probe.format not in formats:
                return _BROKEN
            width, height = probe.size
            if width * height > max_pixels:
                return _TOO_BIG
            probe.verify()
        with Image.open(io.BytesIO(data), formats=formats) as image:
            image.seek(0)
            frame = image.convert("RGBA" if _has_alpha(image) else "RGB")
        frame.thumbnail((max_side, max_side))
        # convert() and thumbnail() carry image.info (ICC profile, JPEG comment...) along.
        clean = Image.new(frame.mode, frame.size)
        clean.paste(frame)
        lossless = clean.mode == "RGBA" or formats[0] in ("PNG", "GIF")
        if lossless:
            out = io.BytesIO()
            clean.save(out, format="PNG", optimize=True)
            if clean.mode == "RGBA" or out.tell() <= _PNG_MAX_BYTES:
                return out.getvalue(), "image/png"
        out = io.BytesIO()
        clean.save(out, format="JPEG", quality=90)
        return out.getvalue(), "image/jpeg"
    except Image.DecompressionBombError:
        return _TOO_BIG
    except Exception:  # any failure on untrusted input
        return _BROKEN


def _has_alpha(image: object) -> bool:
    mode = getattr(image, "mode", "")
    info = getattr(image, "info", {})
    return mode in ("RGBA", "LA", "PA") or (mode == "P" and "transparency" in info)


async def normalize_image(
    data: bytes, source_mime: str, max_pixels: int, max_side: int, time_limit: float
) -> tuple[bytes, str]:
    """Re-encoded image without metadata, and its MIME type (image/png or image/jpeg).

    `source_mime` is what the magic number announced (domain.attachment.detect_kind); only
    that decoder is used. Pillow runs in a killable child process (adapters/files/isolated.py).
    Images over `max_pixels`, broken ones and timeouts raise UnreadableFileError.
    """
    result = await run_isolated(
        _normalize, data, source_mime, max_pixels, max_side, time_limit=time_limit
    )
    if result == TIMEOUT:
        logger.warning("Image normalization timed out")
        raise UnreadableFileError("La imagen tarda demasiado en procesarse")
    if result == _TOO_BIG:
        raise UnreadableFileError("La imagen tiene demasiados píxeles")
    if isinstance(result, str):
        logger.warning("Unreadable image: %s", result)
        raise UnreadableFileError("La imagen está dañada o no se puede leer")
    normalized, mime = result
    return normalized, mime
