"""Application factory and ASGI entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from claimtrace_api.api.health import router as health_router
from claimtrace_api.api.v1.router import api_router
from claimtrace_api.core.config import Settings, get_settings
from claimtrace_api.core.logging import configure_logging
from claimtrace_api.db.session import create_engine, create_session_factory
from claimtrace_api.schemas.errors import ErrorResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the database engine for the lifetime of the process.

    Creating the engine does not open a connection, so startup never blocks on
    PostgreSQL; connectivity is reported by ``GET /ready`` instead.
    """
    settings: Settings = app.state.settings
    app.state.engine = create_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)
    logger.info(
        "application started",
        extra={"environment": settings.environment, "version": settings.app_version},
    )
    try:
        yield
    finally:
        await app.state.engine.dispose()
        logger.info("application stopped")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic 500 while keeping the traceback server-side only."""
    logger.exception(
        "unhandled exception",
        extra={"path": request.url.path, "method": request.method},
    )
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=ErrorResponse(detail="Internal server error").model_dump(),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured FastAPI application."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="Evidence-grounded patent claim analysis API",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
