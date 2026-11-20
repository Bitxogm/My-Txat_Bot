import dataclasses
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from app.core.errors import AppError
from app.domain.chat import ChatMessage, ModelInfo
from app.domain.personality import GenerationParams
from app.ports.llm import LLMProvider

logger = logging.getLogger(__name__)


class NamedProvider(LLMProvider, Protocol):
    name: str


class RoutingLLMProvider:
    """LLMProvider that puts local and remote providers behind one model list.

    Remote models are exposed as "<provider name>/<model id>" (e.g. "groq/openai/gpt-oss-120b")
    and routed by that prefix; everything else goes to the local provider (Ollama). A remote
    provider that fails to list its models is skipped, so the local ones stay usable.
    """

    def __init__(self, local: LLMProvider, remotes: Sequence[NamedProvider] = ()) -> None:
        self._local = local
        self._remotes = {remote.name: remote for remote in remotes}

    async def is_available(self) -> bool:
        return await self._local.is_available()

    async def list_models(self) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        errors: list[AppError] = []
        try:
            models.extend(await self._local.list_models())
        except AppError as exc:
            logger.warning("Local models unavailable: %s", exc.code)
            errors.append(exc)
        for name, remote in self._remotes.items():
            try:
                remote_models = await remote.list_models()
            except AppError as exc:
                logger.warning("Remote provider %s unavailable: %s", name, exc.code)
                errors.append(exc)
                continue
            models.extend(dataclasses.replace(m, name=f"{name}/{m.name}") for m in remote_models)
        if not models and errors:
            raise errors[0]
        return models

    def stream_chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        params: GenerationParams | None = None,
    ) -> AsyncIterator[str]:
        prefix, sep, rest = model.partition("/")
        if sep and prefix in self._remotes:
            return self._remotes[prefix].stream_chat(rest, messages, params)
        return self._local.stream_chat(model, messages, params)
