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
from claimtrace_api.indexing.embeddings.base import EmbeddingProvider
from claimtrace_api.llm.base import LLMProvider
from claimtrace_api.parsing.base import DocumentParser
from claimtrace_api.parsing.claims.base import ClaimParser
from claimtrace_api.services.claim_comparison import ClaimComparisonService
from claimtrace_api.services.claim_indexing import ClaimIndexingService
from claimtrace_api.services.claim_parsing import ClaimParsingService
from claimtrace_api.services.claim_search import ClaimSearchService
from claimtrace_api.services.grounded_generation import GroundedGenerationService
from claimtrace_api.services.ingestion import DocumentIngestionService
from claimtrace_api.services.llm_generation import LLMGenerationService
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


def get_claim_parser(request: Request) -> ClaimParser:
    """Return the configured claim structural parser."""
    return request.app.state.claim_parser


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    """Return the configured embedding provider.

    Built once at startup and shared: the real implementation caches a loaded
    model on the instance, and a per-request provider would reload half a
    gigabyte of weights on every call.
    """
    return request.app.state.embedding_provider


def get_llm_provider(request: Request) -> LLMProvider:
    """Return the configured LLM provider.

    Built once at startup and shared, because the HTTP-backed providers own a
    connection pool: a per-request provider would open and discard a pool on
    every call. Construction contacts nothing, so this is safe even when the
    model server is down.

    Overriding this dependency is how a test injects a fake provider without
    touching configuration.
    """
    return request.app.state.llm_provider


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
PostgresReadyDep = Annotated[bool, Depends(get_postgres_ready)]
StorageDep = Annotated[FileStorage, Depends(get_storage)]
ParserDep = Annotated[DocumentParser, Depends(get_parser)]
ClaimParserDep = Annotated[ClaimParser, Depends(get_claim_parser)]
EmbeddingProviderDep = Annotated[EmbeddingProvider, Depends(get_embedding_provider)]
LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]


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


def get_claim_parsing_service(session: SessionDep, parser: ClaimParserDep) -> ClaimParsingService:
    """Assemble the claim parsing use case for one request."""
    return ClaimParsingService(session=session, parser=parser)


ClaimParsingServiceDep = Annotated[ClaimParsingService, Depends(get_claim_parsing_service)]


def get_claim_indexing_service(
    session: SessionDep, provider: EmbeddingProviderDep
) -> ClaimIndexingService:
    """Assemble the claim indexing use case for one request."""
    return ClaimIndexingService(session=session, provider=provider)


ClaimIndexingServiceDep = Annotated[ClaimIndexingService, Depends(get_claim_indexing_service)]


def get_claim_search_service(
    session: SessionDep, provider: EmbeddingProviderDep, settings: SettingsDep
) -> ClaimSearchService:
    """Assemble the claim search use case for one request."""
    return ClaimSearchService(session=session, provider=provider, settings=settings)


ClaimSearchServiceDep = Annotated[ClaimSearchService, Depends(get_claim_search_service)]


def get_claim_comparison_service(
    session: SessionDep,
    parsing: ClaimParsingServiceDep,
    search: ClaimSearchServiceDep,
    settings: SettingsDep,
) -> ClaimComparisonService:
    """Assemble bounded claim comparison from existing parse and search services."""
    return ClaimComparisonService(
        session=session,
        parsing=parsing,
        search=search,
        settings=settings,
    )


ClaimComparisonServiceDep = Annotated[ClaimComparisonService, Depends(get_claim_comparison_service)]


def get_llm_service(provider: LLMProviderDep, settings: SettingsDep) -> LLMGenerationService:
    """Assemble the generation use case for one request.

    Note what is still absent: no session, and no retrieval service. Provider-
    neutral generation does not touch the database, and Phase 4A-2 kept it that
    way - grounding is a separate service that *composes* this one, so the
    boundary remains a matter of construction rather than of discipline.
    """
    return LLMGenerationService(provider=provider, settings=settings)


LLMServiceDep = Annotated[LLMGenerationService, Depends(get_llm_service)]


def get_grounded_generation_service(
    search: ClaimSearchServiceDep,
    llm: LLMServiceDep,
    session: SessionDep,
    settings: SettingsDep,
) -> GroundedGenerationService:
    """Assemble the evidence-grounded answering use case for one request.

    Composed from the two existing services rather than reaching past them: the
    same ``ClaimSearchService`` the search endpoint uses, and the same
    ``LLMGenerationService`` the diagnostics endpoint uses. The session is here
    for one job only - resolving validated citations against stored page text.
    """
    return GroundedGenerationService(search=search, llm=llm, session=session, settings=settings)


GroundedGenerationServiceDep = Annotated[
    GroundedGenerationService, Depends(get_grounded_generation_service)
]
