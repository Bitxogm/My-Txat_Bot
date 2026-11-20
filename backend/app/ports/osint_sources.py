from typing import Protocol

from app.domain.osint import OsintCategory, OsintSource, OsintSourceFields


class OsintSourceRepository(Protocol):
    async def list_all(
        self, category: OsintCategory | None = None, active_only: bool = False
    ) -> list[OsintSource]:
        """Built-ins first in their fixed order, then custom sources by creation date."""
        ...

    async def get(self, source_id: str) -> OsintSource | None: ...

    async def create(self, fields: OsintSourceFields, is_active: bool = True) -> OsintSource:
        """Always creates a custom (non built-in) source."""
        ...

    async def update(
        self, source_id: str, fields: OsintSourceFields, is_active: bool
    ) -> OsintSource | None:
        """Updates a custom source. None if missing or built-in."""
        ...

    async def set_active(self, source_id: str, is_active: bool) -> OsintSource | None:
        """Works for built-ins too: it's the only change they allow."""
        ...

    async def delete(self, source_id: str) -> bool:
        """Deletes a custom source. False if missing or built-in."""
        ...

    async def seed_builtins(self, builtins: dict[str, OsintSourceFields]) -> None:
        """Create or refresh the built-ins without touching is_active (idempotent)."""
        ...
