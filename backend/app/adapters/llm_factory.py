"""Builds the LLMProvider from the settings: Ollama, plus the cloud provider when configured.
Shared by the app (main.py) and the evaluation command (app.cli eval)."""

import logging

import httpx

from app.adapters.ollama.provider import (
    OllamaProvider,
    build_chat_timeout,
    build_ollama_client,
)
from app.adapters.openai_compat.provider import (
    OpenAICompatibleProvider,
    build_openai_compatible_client,
)
from app.adapters.routing import RoutingLLMProvider
from app.core.config import Settings

logger = logging.getLogger(__name__)


def build_llm_provider(
    settings: Settings, think: bool | None = None
) -> tuple[RoutingLLMProvider, list[httpx.AsyncClient]]:
    """The provider and the HTTP clients the caller must close. `think` overrides OLLAMA_THINK."""
    client = build_ollama_client(settings.ollama_base_url, settings.ollama_timeout_seconds)
    clients = [client]
    chat_timeout = build_chat_timeout(
        settings.ollama_timeout_seconds, settings.ollama_chat_read_timeout_seconds
    )
    ollama = OllamaProvider(
        client, chat_timeout, think=settings.ollama_think if think is None else think
    )
    remotes: list[OpenAICompatibleProvider] = []
    if settings.cloud_enabled:
        cloud_client = build_openai_compatible_client(
            settings.cloud_base_url,
            settings.cloud_api_key.get_secret_value(),
            settings.cloud_timeout_seconds,
        )
        clients.append(cloud_client)
        remotes.append(
            OpenAICompatibleProvider(
                cloud_client,
                settings.cloud_name,
                allowed_models=settings.cloud_model_list,
                vision_models=settings.cloud_vision_model_list,
                chat_timeout=build_chat_timeout(
                    settings.cloud_timeout_seconds, settings.ollama_chat_read_timeout_seconds
                ),
            )
        )
        logger.info("Cloud provider enabled: %s", settings.cloud_name)
    return RoutingLLMProvider(ollama, remotes), clients
