from typing import Annotated

from fastapi import Cookie, Depends, Request

from app.core.auth import SESSION_COOKIE, AuthService, Session
from app.core.config import Settings
from app.ports.llm import LLMProvider


def get_llm_provider(request: Request) -> LLMProvider:
    provider: LLMProvider = request.app.state.llm_provider
    return provider


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_auth_service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth_service
    return service


def require_session(
    auth: Annotated[AuthService, Depends(get_auth_service)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Session:
    return auth.authenticate(token)
