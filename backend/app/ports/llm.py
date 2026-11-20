from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from app.domain.chat import ChatMessage, ModelInfo
from app.domain.personality import GenerationParams


class LLMProvider(Protocol):
    """Contract the backend uses to talk to a model server (ADR-002).

    Implementations raise ModelUnavailableError / ModelNotFoundError from app.core.errors.
    """

    async def is_available(self) -> bool:
        """True if the model server answers. Never raises."""
        ...

    async def list_models(self) -> list[ModelInfo]: ...

    def stream_chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        params: GenerationParams | None = None,
    ) -> AsyncIterator[str]:
        """Yield the assistant reply in text chunks as the model produces them.

        `params` (temperature, top_p, num_ctx) are applied when the backend supports them and
        silently ignored when it doesn't; None values keep the model's defaults.
        """
        ...
