"""Images built in memory with Pillow (no binary fixtures in the repo)."""

import io
import struct
import zlib

from PIL import Image


def png(width: int = 32, height: int = 24, mode: str = "RGB") -> bytes:
    out = io.BytesIO()
    Image.new(mode, (width, height), (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30)).save(
        out, format="PNG"
    )
    return out.getvalue()


def jpeg_with_exif(width: int = 40, height: int = 30) -> bytes:
    image = Image.new("RGB", (width, height), (10, 120, 200))
    exif = Image.Exif()
    exif[0x010F] = "CamaraSecreta"  # Make
    exif[0x8825] = {1: "N", 2: (40.0, 25.0, 0.0)}  # GPSInfo
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


def animated_gif() -> bytes:
    frames = [Image.new("P", (16, 16), i) for i in (1, 2, 3)]
    out = io.BytesIO()
    frames[0].save(out, format="GIF", save_all=True, append_images=frames[1:])
    return out.getvalue()


def webp() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (20, 20), (0, 200, 0)).save(out, format="WEBP")
    return out.getvalue()


def png_claiming(width: int, height: int) -> bytes:
    """A tiny PNG whose header claims a huge size (decompression bomb)."""
    data = bytearray(png(1, 1))
    ihdr = data.index(b"IHDR")
    data[ihdr + 4 : ihdr + 12] = struct.pack(">II", width, height)
    crc = zlib.crc32(bytes(data[ihdr : ihdr + 17])) & 0xFFFFFFFF
    data[ihdr + 17 : ihdr + 21] = struct.pack(">I", crc)
    return bytes(data)


def jpeg_with_comment(text: bytes) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (20, 20), (1, 2, 3)).save(out, format="JPEG", comment=text)
    return out.getvalue()


def png_with_icc(marker: bytes) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (20, 20), (1, 2, 3, 100)).save(out, format="PNG", icc_profile=marker * 8)
    return out.getvalue()


def noisy_png(side: int = 1400) -> bytes:
    """Random pixels: huge as PNG, the case where a JPEG is the better re-encode."""
    import os

    out = io.BytesIO()
    Image.frombytes("RGB", (side, side), os.urandom(side * side * 3)).save(out, format="PNG")
    return out.getvalue()


def png_header_over_pcd() -> bytes:
    """Starts like a PNG but is a Kodak PhotoCD file: Pillow opens it as PCD if allowed to
    fall back to other decoders."""
    data = bytearray(b"\x89PNG\r\n\x1a\n" + b"\x00" * 4000)
    data[2048:2055] = b"PCD_IPI"
    return bytes(data)
