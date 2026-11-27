from typing import Annotated

from fastapi import Cookie, Depends, Request

from app.core.auth import SESSION_COOKIE, AuthService, Session
from app.core.config import Settings
from app.ports.attachments import AttachmentRepository
from app.ports.conversations import ConversationRepository
from app.ports.feedback import FeedbackRepository
from app.ports.file_storage import FileStorage
from app.ports.llm import LLMProvider
from app.ports.memories import AppSettingsRepository, MemoryRepository
from app.ports.osint_sources import OsintSourceRepository
from app.ports.personalities import PersonalityRepository


def get_llm_provider(request: Request) -> LLMProvider:
    provider: LLMProvider = request.app.state.llm_provider
    return provider


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_conversation_repository(request: Request) -> ConversationRepository:
    repository: ConversationRepository = request.app.state.conversations
    return repository


def get_feedback_repository(request: Request) -> FeedbackRepository:
    repository: FeedbackRepository = request.app.state.feedback
    return repository


def get_memory_repository(request: Request) -> MemoryRepository:
    repository: MemoryRepository = request.app.state.memories
    return repository


def get_app_settings_repository(request: Request) -> AppSettingsRepository:
    repository: AppSettingsRepository = request.app.state.app_settings
    return repository


def get_personality_repository(request: Request) -> PersonalityRepository:
    repository: PersonalityRepository = request.app.state.personalities
    return repository


def get_osint_source_repository(request: Request) -> OsintSourceRepository:
    repository: OsintSourceRepository = request.app.state.osint_sources
    return repository


def get_attachment_repository(request: Request) -> AttachmentRepository:
    repository: AttachmentRepository = request.app.state.attachments
    return repository


def get_file_storage(request: Request) -> FileStorage:
    storage: FileStorage = request.app.state.file_storage
    return storage


def get_auth_service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth_service
    return service


def require_session(
    auth: Annotated[AuthService, Depends(get_auth_service)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Session:
    return auth.authenticate(token)
