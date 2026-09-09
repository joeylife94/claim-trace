"""D4 source-verifiable patent description evidence endpoints."""

from __future__ import annotations

import uuid
from http import HTTPStatus

from fastapi import APIRouter, Response

from claimtrace_api.api.deps import DescriptionEvidenceServiceDep, SettingsDep
from claimtrace_api.schemas.descriptions import (
    DescriptionDerivationResponse,
    DescriptionIndexResponse,
    DescriptionSearchRequest,
    DescriptionSearchResponse,
    DescriptionSearchResultResponse,
    DescriptionSegmentResponse,
)
from claimtrace_api.schemas.errors import ApiErrorResponse
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.schemas.retrieval import RetrievalProfileResponse
from claimtrace_api.services.description_evidence import (
    EVIDENCE_KIND,
    SEGMENTER_NAME,
    SEGMENTER_VERSION,
    DescriptionDerivationOutcome,
    DescriptionSearchOutcome,
    DescriptionSegment,
)

router = APIRouter(tags=["description evidence"])


@router.post(
    "/documents/{document_id}/descriptions/derive",
    response_model=DescriptionDerivationResponse,
    status_code=HTTPStatus.CREATED,
    summary="Derive source-verifiable description segments",
    responses={
        HTTPStatus.NOT_FOUND: {"model": ApiErrorResponse},
        HTTPStatus.CONFLICT: {"model": ApiErrorResponse},
    },
)
async def derive_description(
    document_id: str,
    response: Response,
    service: DescriptionEvidenceServiceDep,
) -> DescriptionDerivationResponse:
    outcome = await service.derive(_document_uuid(document_id))
    if not outcome.created:
        response.status_code = HTTPStatus.OK
    return _derivation_response(outcome)


@router.post(
    "/documents/{document_id}/descriptions/index",
    response_model=DescriptionIndexResponse,
    status_code=HTTPStatus.CREATED,
    summary="Index persisted description evidence",
    responses={
        HTTPStatus.NOT_FOUND: {"model": ApiErrorResponse},
        HTTPStatus.CONFLICT: {"model": ApiErrorResponse},
    },
)
async def index_description(
    document_id: str,
    response: Response,
    service: DescriptionEvidenceServiceDep,
) -> DescriptionIndexResponse:
    outcome = await service.index(_document_uuid(document_id))
    if not outcome.created:
        response.status_code = HTTPStatus.OK
    profile = outcome.profile
    return DescriptionIndexResponse(
        status=outcome.status,
        profile=RetrievalProfileResponse(
            embedding_provider=profile.embedding_provider,
            embedding_model=profile.embedding_model,
            embedding_model_version=profile.embedding_model_version,
            embedding_dimension=profile.embedding_dimension,
            vectors_normalized=profile.vectors_normalized,
            normalization_version=profile.normalization_version,
            lexical_strategy=profile.lexical_strategy,
            lexical_strategy_version=profile.lexical_strategy_version,
            rrf_k=service._settings.rrf_k,
        ),
        indexed_segment_count=outcome.indexed_segment_count,
        warnings=outcome.warnings,
        created=outcome.created,
    )


@router.post(
    "/search/descriptions",
    response_model=DescriptionSearchResponse,
    summary="Search persisted patent description evidence",
    description=(
        "Bounded dense/lexical/hybrid retrieval over description segments derived from persisted "
        "page text. Every result is explicitly `description` evidence and carries the canonical "
        "page-relative source span plus a document-detail URL that opens that exact range."
    ),
    responses={
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ApiErrorResponse},
    },
)
async def search_descriptions(
    request: DescriptionSearchRequest,
    service: DescriptionEvidenceServiceDep,
    settings: SettingsDep,
) -> DescriptionSearchResponse:
    outcome = await service.search(
        query=request.query,
        mode=request.mode,
        document_ids=request.document_ids or None,
        top_k=min(request.top_k, settings.search_top_k_max),
        dense_candidate_count=min(
            request.dense_candidate_count, settings.search_candidate_count_max
        ),
        lexical_candidate_count=min(
            request.lexical_candidate_count, settings.search_candidate_count_max
        ),
    )
    return _search_response(outcome, rrf_k=settings.rrf_k)


def _derivation_response(outcome: DescriptionDerivationOutcome) -> DescriptionDerivationResponse:
    return DescriptionDerivationResponse(
        run_id=outcome.run_id,
        status=outcome.status,
        segmenter_name=SEGMENTER_NAME,
        segmenter_version=SEGMENTER_VERSION,
        segment_count=len(outcome.segments),
        warnings=outcome.warnings,
        created=outcome.created,
        segments=[_segment_response(segment) for segment in outcome.segments],
    )


def _segment_response(segment: DescriptionSegment) -> DescriptionSegmentResponse:
    locator = SourceLocator(
        document_id=segment.document_id,
        page_number=segment.page_number,
        start_char=segment.start_char,
        end_char=segment.end_char,
    )
    return DescriptionSegmentResponse(
        id=segment.id,
        evidence_kind=EVIDENCE_KIND,
        segment_index=segment.segment_index,
        section_heading=segment.section_heading,
        text=segment.text,
        source_span=locator,
        source_url=_source_url(locator),
    )


def _search_response(outcome: DescriptionSearchOutcome, *, rrf_k: int) -> DescriptionSearchResponse:
    profile = outcome.profile
    return DescriptionSearchResponse(
        mode=outcome.mode,
        profile=RetrievalProfileResponse(
            embedding_provider=profile.embedding_provider,
            embedding_model=profile.embedding_model,
            embedding_model_version=profile.embedding_model_version,
            embedding_dimension=profile.embedding_dimension,
            vectors_normalized=profile.vectors_normalized,
            normalization_version=profile.normalization_version,
            lexical_strategy=profile.lexical_strategy,
            lexical_strategy_version=profile.lexical_strategy_version,
            rrf_k=rrf_k,
        ),
        dense_candidate_count=outcome.dense_candidate_count,
        lexical_candidate_count=outcome.lexical_candidate_count,
        result_count=len(outcome.results),
        results=[
            DescriptionSearchResultResponse(
                id=result.segment.id,
                evidence_kind=EVIDENCE_KIND,
                segment_index=result.segment.segment_index,
                section_heading=result.segment.section_heading,
                text=result.segment.text,
                source_span=SourceLocator(
                    document_id=result.segment.document_id,
                    page_number=result.segment.page_number,
                    start_char=result.segment.start_char,
                    end_char=result.segment.end_char,
                ),
                source_url=_source_url(
                    SourceLocator(
                        document_id=result.segment.document_id,
                        page_number=result.segment.page_number,
                        start_char=result.segment.start_char,
                        end_char=result.segment.end_char,
                    )
                ),
                document_id=result.segment.document_id,
                document_filename=result.document_filename,
                dense_rank=result.dense_rank,
                dense_score=result.dense_score,
                lexical_rank=result.lexical_rank,
                lexical_score=result.lexical_score,
                fused_rank=result.fused_rank,
                fused_score=result.fused_score,
            )
            for result in outcome.results
        ],
    )


def _source_url(locator: SourceLocator) -> str:
    return (
        f"/documents/{locator.document_id}?page={locator.page_number}"
        f"&start={locator.start_char}&end={locator.end_char}"
    )


def _document_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError("document_id must be a UUID") from exc
