from typing import Protocol


class FileStorage(Protocol):
    """Raw bytes of uploaded files, addressed by a server-generated key (never a client path)."""

    async def save(self, data: bytes) -> str:
        """Store the bytes and return the new key."""
        ...

    async def delete(self, key: str) -> None:
        """Remove the file; a missing file is not an error."""
        ...

    async def keys(self) -> list[str]:
        """Keys of every stored file (to sweep orphans)."""
        ...
