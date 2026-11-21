import asyncio
import os
import re
import uuid
from pathlib import Path

_KEY = re.compile(r"^[0-9a-f]{32}$")


class LocalFileStorage:
    """FileStorage on a local directory (data/uploads, a Docker volume).

    Keys are uuid4 hex generated here; anything else is refused, so a key can never point
    outside the directory. Files are written 0600 and never executed or served directly.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, key: str) -> Path:
        if not _KEY.fullmatch(key):
            raise ValueError("invalid storage key")
        return self._root / key

    async def save(self, data: bytes) -> str:
        key = uuid.uuid4().hex
        path = self._path(key)
        await asyncio.to_thread(self._write, path, data)
        return key

    def _write(self, path: Path, data: bytes) -> None:
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self._root, 0o700)  # mkdir's mode is masked by umask and skipped if it exists
        # O_EXCL: never overwrite; O_NOFOLLOW: never write through a planted symlink.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)

    async def keys(self) -> list[str]:
        return await asyncio.to_thread(self._list)

    def _list(self) -> list[str]:
        if not self._root.is_dir():
            return []
        return [p.name for p in self._root.iterdir() if _KEY.fullmatch(p.name) and p.is_file()]


async def sweep_orphans(storage: LocalFileStorage, known: set[str]) -> int:
    """Delete stored files no attachment row points to (left by a crash between saving the file
    and inserting its row, or a failed delete). Run at startup, before any upload."""
    removed = 0
    for key in await storage.keys():
        if key not in known:
            await storage.delete(key)
            removed += 1
    return removed
