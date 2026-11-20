from typing import Protocol


class LLMProvider(Protocol):
    """Contract the backend uses to talk to a model server (ADR-002)."""

    async def is_available(self) -> bool:
        """True if the model server answers. Never raises."""
        ...
