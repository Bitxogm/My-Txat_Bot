from datetime import datetime
from typing import Protocol

from app.domain.memory import Memory, MemoryCategory


class MemoryRepository(Protocol):
    async def list_all(self, now: datetime) -> list[Memory]:
        """Every entry (active, inactive and archived), after archiving the expired ones."""
        ...

    async def in_use(self, now: datetime) -> list[Memory]:
        """The entries sent to the model: active and not archived (expired ones archived first)."""
        ...

    async def get(self, memory_id: str) -> Memory | None: ...

    async def create(self, category: MemoryCategory, text: str, is_active: bool) -> Memory: ...

    async def replace(
        self, memory_id: str, category: MemoryCategory, text: str, is_active: bool
    ) -> Memory | None:
        """Full update. Takes the entry out of the archive and renews its date."""
        ...

    async def delete(self, memory_id: str) -> bool: ...


class AppSettingsRepository(Protocol):
    async def memory_to_remote(self) -> bool:
        """Whether the memory is also sent to cloud models (off by default)."""
        ...

    async def set_memory_to_remote(self, enabled: bool) -> None: ...
