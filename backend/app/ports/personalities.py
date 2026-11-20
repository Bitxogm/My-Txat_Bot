from typing import Protocol

from app.domain.personality import Personality, PersonalityFields


class PersonalityRepository(Protocol):
    async def list_all(self) -> list[Personality]:
        """Built-ins first in their fixed order, then copies by creation date."""
        ...

    async def get(self, personality_id: str) -> Personality | None: ...

    async def create(self, fields: PersonalityFields) -> Personality:
        """Always creates an editable (non built-in) personality."""
        ...

    async def update(self, personality_id: str, fields: PersonalityFields) -> Personality | None:
        """Updates a non built-in personality. Returns None if missing or built-in."""
        ...

    async def delete(self, personality_id: str) -> bool:
        """Deletes a non built-in personality. False if missing or built-in."""
        ...

    async def seed_builtins(self, builtins: dict[str, PersonalityFields]) -> None:
        """Create or refresh the built-ins (idempotent)."""
        ...
