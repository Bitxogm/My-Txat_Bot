from fastapi import Request

from app.core.config import Settings
from app.ports.llm import LLMProvider


def get_llm_provider(request: Request) -> LLMProvider:
    provider: LLMProvider = request.app.state.llm_provider
    return provider


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings
