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
    ollama_client = build_ollama_client(settings.ollama_base_url, settings.ollama_timeout_seconds)
    clients = [ollama_client]
    chat_timeout = build_chat_timeout(
        settings.ollama_timeout_seconds, settings.ollama_chat_read_timeout_seconds
    )
    ollama = OllamaProvider(
        ollama_client,
        chat_timeout,
        think=settings.ollama_think if think is None else think,
        keep_alive=settings.ollama_keep_alive,
    )
    for warning in settings.config_warnings:
        logger.warning("%s", warning)
    remotes: list[OpenAICompatibleProvider] = []
    for config in settings.provider_list:
        client = build_openai_compatible_client(
            config.base_url, config.api_key.get_secret_value(), settings.provider_timeout_seconds
        )
        clients.append(client)
        remotes.append(
            OpenAICompatibleProvider(
                client,
                config.name,
                allowed_models=config.models,
                vision_models=config.vision_models,
                chat_timeout=build_chat_timeout(
                    settings.provider_timeout_seconds, settings.ollama_chat_read_timeout_seconds
                ),
                local=config.local,
                key_variable=config.key_variable,
                reasoning_effort=config.reasoning_effort,
            )
        )
        logger.info("Provider enabled: %s (%s)", config.name, "local" if config.local else "remote")
    return RoutingLLMProvider(ollama, remotes), clients
