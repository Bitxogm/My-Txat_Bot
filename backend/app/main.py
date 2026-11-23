import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.files.local_storage import LocalFileStorage, sweep_orphans
from app.adapters.llm_factory import build_llm_provider
from app.adapters.sqlite.attachments import SqliteAttachmentRepository
from app.adapters.sqlite.conversations import SqliteConversationRepository
from app.adapters.sqlite.database import connect, sqlite_path
from app.adapters.sqlite.osint_sources import SqliteOsintSourceRepository
from app.adapters.sqlite.personalities import SqlitePersonalityRepository
from app.api.dependencies import require_session
from app.api.routes import (
    attachments,
    auth,
    chat,
    conversations,
    health,
    models,
    osint_sources,
    personalities,
)
from app.core.auth import AuthService
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.domain.builtin_osint_sources import BUILTIN_OSINT_SOURCES
from app.domain.builtin_personalities import BUILTIN_PERSONALITIES
from app.maintenance import sweep_stale_drafts

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        llm, clients = build_llm_provider(settings)
        app.state.llm_provider = llm
        db = await connect(sqlite_path(settings.database_url))
        app.state.conversations = SqliteConversationRepository(db)
        attachment_repo = SqliteAttachmentRepository(db)
        app.state.attachments = attachment_repo
        file_storage = LocalFileStorage(Path(settings.upload_dir))
        app.state.file_storage = file_storage
        try:
            drafts = await sweep_stale_drafts(
                app.state.conversations, attachment_repo, file_storage
            )
            if drafts:
                logger.info("Removed %d stale draft conversation(s)", drafts)
        except Exception as exc:  # housekeeping must never stop the backend from starting
            logger.warning("Could not sweep draft conversations: %s", type(exc).__name__)
        try:
            orphans = await sweep_orphans(file_storage, set(await attachment_repo.storage_keys()))
            if orphans:
                logger.info("Removed %d orphan upload file(s)", orphans)
        except OSError as exc:
            logger.warning("Could not sweep the upload folder: %s", type(exc).__name__)
        personality_repo = SqlitePersonalityRepository(db)
        await personality_repo.seed_builtins(BUILTIN_PERSONALITIES)
        app.state.personalities = personality_repo
        osint_repo = SqliteOsintSourceRepository(db)
        await osint_repo.seed_builtins(BUILTIN_OSINT_SOURCES)
        app.state.osint_sources = osint_repo
        logger.info("Backend started (env=%s)", settings.app_env)
        try:
            yield
        finally:
            await db.close()
            for http_client in clients:
                await http_client.aclose()

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
    app.include_router(attachments.router, prefix="/api", dependencies=protected)
    app.include_router(personalities.router, prefix="/api", dependencies=protected)
    app.include_router(osint_sources.router, prefix="/api", dependencies=protected)
    return app


app = create_app()
