"""Shared FastAPI dependencies.

Every external resource reaches a route handler through one of these functions,
which keeps handlers trivially overridable in tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.db.health import check_postgres
from claimtrace_api.db.session import session_scope
from claimtrace_api.parsing.base import DocumentParser
from claimtrace_api.services.ingestion import DocumentIngestionService
from claimtrace_api.storage.base import FileStorage


def get_app_settings(request: Request) -> Settings:
    """Return the settings the application was built with.

    Reads from application state rather than the module-level singleton so that a
    test (or an embedding process) can construct an app with explicit settings.
    """
    return request.app.state.settings


def get_engine(request: Request) -> AsyncEngine:
    """Return the engine created during application startup."""
    return request.app.state.engine


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session."""
    async for session in session_scope(request.app.state.session_factory):
        yield session


async def get_postgres_ready(engine: Annotated[AsyncEngine, Depends(get_engine)]) -> bool:
    """Report whether PostgreSQL is reachable. Overridden in tests."""
    return await check_postgres(engine)


def get_storage(request: Request) -> FileStorage:
    """Return the storage backend created during application startup."""
    return request.app.state.storage


def get_parser(request: Request) -> DocumentParser:
    """Return the configured document parser.

    A single implementation today; when a second one exists this becomes the
    selection point, and no route handler changes.
    """
    return request.app.state.parser


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
PostgresReadyDep = Annotated[bool, Depends(get_postgres_ready)]
StorageDep = Annotated[FileStorage, Depends(get_storage)]
ParserDep = Annotated[DocumentParser, Depends(get_parser)]


def get_ingestion_service(
    session: SessionDep,
    storage: StorageDep,
    parser: ParserDep,
    settings: SettingsDep,
) -> DocumentIngestionService:
    """Assemble the ingestion use case for one request."""
    return DocumentIngestionService(
        session=session, storage=storage, parser=parser, settings=settings
    )


IngestionServiceDep = Annotated[DocumentIngestionService, Depends(get_ingestion_service)]
