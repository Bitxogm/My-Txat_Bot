import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from app.adapters.sqlite.conversations import SqliteConversationRepository
from app.adapters.sqlite.database import connect, sqlite_path
from app.adapters.sqlite.personalities import SqlitePersonalityRepository
from app.api.dependencies import require_session
from app.api.routes import auth, chat, conversations, health, models, personalities
from app.core.auth import AuthService
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.domain.builtin_personalities import BUILTIN_PERSONALITIES

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = build_ollama_client(settings.ollama_base_url, settings.ollama_timeout_seconds)
        chat_timeout = build_chat_timeout(
            settings.ollama_timeout_seconds, settings.ollama_chat_read_timeout_seconds
        )
        ollama = OllamaProvider(client, chat_timeout, think=settings.ollama_think)
        remotes: list[OpenAICompatibleProvider] = []
        cloud_client = None
        if settings.cloud_enabled:
            cloud_client = build_openai_compatible_client(
                settings.cloud_base_url,
                settings.cloud_api_key.get_secret_value(),
                settings.cloud_timeout_seconds,
            )
            remotes.append(
                OpenAICompatibleProvider(
                    cloud_client,
                    settings.cloud_name,
                    allowed_models=settings.cloud_model_list,
                    chat_timeout=build_chat_timeout(
                        settings.cloud_timeout_seconds, settings.ollama_chat_read_timeout_seconds
                    ),
                )
            )
            logger.info("Cloud provider enabled: %s", settings.cloud_name)
        app.state.llm_provider = RoutingLLMProvider(ollama, remotes)
        db = await connect(sqlite_path(settings.database_url))
        app.state.conversations = SqliteConversationRepository(db)
        personality_repo = SqlitePersonalityRepository(db)
        await personality_repo.seed_builtins(BUILTIN_PERSONALITIES)
        app.state.personalities = personality_repo
        logger.info("Backend started (env=%s)", settings.app_env)
        try:
            yield
        finally:
            await db.close()
            await client.aclose()
            if cloud_client is not None:
                await cloud_client.aclose()

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="Txat_bot API",
        lifespan=lifespan,
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
    )

    app.state.settings = settings
    app.state.auth_service = AuthService(settings)
    if not app.state.auth_service.is_configured:
        logger.warning(
            "Login not configured (AUTH_USERNAME, a valid argon2id AUTH_PASSWORD_HASH in single"
            " quotes, SESSION_SECRET >= 32 chars): protected endpoints will answer 503"
        )
    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    # Added last so it is the outermost user middleware: CORS preflights and errors get an ID too.
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    protected = [Depends(require_session)]
    app.include_router(models.router, prefix="/api", dependencies=protected)
    app.include_router(chat.router, prefix="/api", dependencies=protected)
    app.include_router(conversations.router, prefix="/api", dependencies=protected)
    app.include_router(personalities.router, prefix="/api", dependencies=protected)
    return app


app = create_app()
