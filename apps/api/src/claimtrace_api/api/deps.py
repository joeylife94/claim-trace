"""Shared FastAPI dependencies."""

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
from claimtrace_api.parsing.elements import DeterministicElementParser
from claimtrace_api.services.claim_comparison import ClaimComparisonService
from claimtrace_api.services.claim_element_reviews import ClaimElementReviewService
from claimtrace_api.services.claim_elements import ClaimElementService
from claimtrace_api.services.claim_indexing import ClaimIndexingService
from claimtrace_api.services.claim_parsing import ClaimParsingService
from claimtrace_api.services.claim_search import ClaimSearchService
from claimtrace_api.services.grounded_generation import GroundedGenerationService
from claimtrace_api.services.ingestion import DocumentIngestionService
from claimtrace_api.services.llm_generation import LLMGenerationService
from claimtrace_api.storage.base import FileStorage


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_engine(request: Request) -> AsyncEngine:
    return request.app.state.engine


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_scope(request.app.state.session_factory):
        yield session


async def get_postgres_ready(engine: Annotated[AsyncEngine, Depends(get_engine)]) -> bool:
    return await check_postgres(engine)


def get_storage(request: Request) -> FileStorage:
    return request.app.state.storage


def get_parser(request: Request) -> DocumentParser:
    return request.app.state.parser


def get_claim_parser(request: Request) -> ClaimParser:
    return request.app.state.claim_parser


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    return request.app.state.embedding_provider


def get_llm_provider(request: Request) -> LLMProvider:
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
    return DocumentIngestionService(
        session=session, storage=storage, parser=parser, settings=settings
    )


IngestionServiceDep = Annotated[DocumentIngestionService, Depends(get_ingestion_service)]


def get_claim_parsing_service(session: SessionDep, parser: ClaimParserDep) -> ClaimParsingService:
    return ClaimParsingService(session=session, parser=parser)


ClaimParsingServiceDep = Annotated[ClaimParsingService, Depends(get_claim_parsing_service)]


def get_claim_element_service(session: SessionDep) -> ClaimElementService:
    return ClaimElementService(session=session, parser=DeterministicElementParser())


ClaimElementServiceDep = Annotated[ClaimElementService, Depends(get_claim_element_service)]


def get_claim_element_review_service(session: SessionDep) -> ClaimElementReviewService:
    return ClaimElementReviewService(session=session)


ClaimElementReviewServiceDep = Annotated[
    ClaimElementReviewService, Depends(get_claim_element_review_service)
]


def get_claim_indexing_service(
    session: SessionDep, provider: EmbeddingProviderDep
) -> ClaimIndexingService:
    return ClaimIndexingService(session=session, provider=provider)


ClaimIndexingServiceDep = Annotated[ClaimIndexingService, Depends(get_claim_indexing_service)]


def get_claim_search_service(
    session: SessionDep, provider: EmbeddingProviderDep, settings: SettingsDep
) -> ClaimSearchService:
    return ClaimSearchService(session=session, provider=provider, settings=settings)


ClaimSearchServiceDep = Annotated[ClaimSearchService, Depends(get_claim_search_service)]


def get_claim_comparison_service(
    session: SessionDep,
    parsing: ClaimParsingServiceDep,
    search: ClaimSearchServiceDep,
    settings: SettingsDep,
) -> ClaimComparisonService:
    return ClaimComparisonService(
        session=session,
        parsing=parsing,
        search=search,
        settings=settings,
    )


ClaimComparisonServiceDep = Annotated[ClaimComparisonService, Depends(get_claim_comparison_service)]


def get_llm_service(provider: LLMProviderDep, settings: SettingsDep) -> LLMGenerationService:
    return LLMGenerationService(provider=provider, settings=settings)


LLMServiceDep = Annotated[LLMGenerationService, Depends(get_llm_service)]


def get_grounded_generation_service(
    search: ClaimSearchServiceDep,
    llm: LLMServiceDep,
    session: SessionDep,
    settings: SettingsDep,
) -> GroundedGenerationService:
    return GroundedGenerationService(search=search, llm=llm, session=session, settings=settings)


GroundedGenerationServiceDep = Annotated[
    GroundedGenerationService, Depends(get_grounded_generation_service)
]
