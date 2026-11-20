import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.ollama.provider import OllamaProvider, build_ollama_client
from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = build_ollama_client(settings.ollama_base_url, settings.ollama_timeout_seconds)
        app.state.llm_provider = OllamaProvider(client)
        logger.info("Backend started (env=%s)", settings.app_env)
        try:
            yield
        finally:
            await client.aclose()

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="Txat_bot API",
        lifespan=lifespan,
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
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
    return app


app = create_app()
