"""Application factory and ASGI entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from claimtrace_api.api.health import router as health_router
from claimtrace_api.api.v1.router import api_router
from claimtrace_api.core.config import Settings, get_settings
from claimtrace_api.core.errors import AppError
from claimtrace_api.core.logging import configure_logging
from claimtrace_api.db.session import create_engine, create_session_factory
from claimtrace_api.indexing.embeddings.base import EmbeddingProvider
from claimtrace_api.indexing.embeddings.fake import FakeEmbeddingProvider
from claimtrace_api.llm.registry import build_llm_provider
from claimtrace_api.parsing.claims.korean_rules import KoreanRuleBasedClaimParser
from claimtrace_api.parsing.pymupdf_parser import PyMuPDFDocumentParser
from claimtrace_api.schemas.documents import DocumentResponse, IngestionErrorResponse
from claimtrace_api.schemas.errors import ApiErrorResponse, ErrorResponse
from claimtrace_api.services.ingestion import DocumentIngestionError
from claimtrace_api.storage.local import LocalFileStorage

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
    # Created once: both are stateless and cheap to share across requests.
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    app.state.storage = LocalFileStorage(settings.storage_root)
    app.state.parser = PyMuPDFDocumentParser()
    app.state.claim_parser = KoreanRuleBasedClaimParser()
    # Constructed, not loaded: the real provider reads its weights on first use,
    # so an application with nothing to index never pays for the model and
    # startup never blocks on half a gigabyte of disk.
    app.state.embedding_provider = build_embedding_provider(settings)
    # Also constructed rather than connected: an unreachable model server must
    # not stop the application from starting, because nothing outside the LLM
    # diagnostics endpoints depends on it. Reachability is reported by
    # GET /api/v1/llm/status instead.
    app.state.llm_provider = build_llm_provider(settings)
    logger.info(
        "application started",
        extra={
            "environment": settings.environment,
            "version": settings.app_version,
            "llm_provider": settings.llm_provider,
        },
    )
    try:
        yield
    finally:
        # Before the engine: releases the provider's HTTP connection pool while
        # the loop is still running, which avoids an "unclosed client" warning
        # on shutdown.
        await app.state.llm_provider.aclose()
        await app.state.engine.dispose()
        logger.info("application stopped")


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Select the embedding provider named by configuration.

    The import of the sentence-transformers implementation is deferred into the
    branch that needs it: it pulls torch through an optional extra, and an
    installation running with ``EMBEDDING_PROVIDER=fake`` must not need it
    present at all.
    """
    if settings.embedding_provider == "fake":
        return FakeEmbeddingProvider(dimension=settings.embedding_dimension)

    from claimtrace_api.indexing.embeddings.sentence_transformers import (
        SentenceTransformerEmbeddingProvider,
    )

    return SentenceTransformerEmbeddingProvider(
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        cache_dir=settings.embedding_cache_dir,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
    )


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate a domain failure into its documented status and error code.

    The message is written for the end user and carries no path, query, document
    text, or claim text. When an upload failed after the file was stored, the
    traceable document record travels with the error.
    """
    assert isinstance(exc, AppError)  # noqa: S101 - handler is registered for this type
    logger.info(
        "request rejected",
        extra={"path": request.url.path, "error_code": exc.code.value},
    )

    # Two shapes, matching the two documented schemas: the ingestion envelope
    # carries the stored document, everything else is detail plus code. Emitting
    # a null "document" on a claim error would contradict its declared response.
    payload: ApiErrorResponse | IngestionErrorResponse
    if isinstance(exc, DocumentIngestionError):
        payload = IngestionErrorResponse(
            detail=exc.message,
            error_code=exc.code.value,
            document=DocumentResponse.model_validate(exc.document),
        )
    else:
        payload = ApiErrorResponse(detail=exc.message, error_code=exc.code.value)

    return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(payload))


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

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
