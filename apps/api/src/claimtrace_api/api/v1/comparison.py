"""Bounded claim comparison endpoint.

The endpoint compares one stored target claim with claims retrieved only from one
selected reference document. It reports textual correspondence and source
provenance; it does not make legal determinations.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter

from claimtrace_api.api.deps import ClaimComparisonServiceDep, SettingsDep
from claimtrace_api.schemas.comparison import (
    ClaimComparisonRequest,
    ClaimComparisonResponse,
    ComparisonClaimResponse,
    ComparisonMatchResponse,
)
from claimtrace_api.schemas.errors import ApiErrorResponse
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.schemas.retrieval import RetrievalProfileResponse
from claimtrace_api.services.claim_comparison import ClaimComparisonOutcome

router = APIRouter(prefix="/compare", tags=["comparison"])


@router.post(
    "/claims",
    response_model=ClaimComparisonResponse,
    summary="Compare one claim against one reference document",
    description=(
        "Uses the persisted target claim text as the retrieval query and restricts "
        "candidate retrieval to exactly one selected reference document. Returned "
        "matches are textual correspondences with canonical source locators. The "
        "response does not determine infringement, validity, novelty, equivalence, "
        "inventive step, or patentability."
    ),
    responses={
        HTTPStatus.BAD_REQUEST: {"model": ApiErrorResponse},
        HTTPStatus.NOT_FOUND: {"model": ApiErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ApiErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    },
)
async def compare_claims(
    request: ClaimComparisonRequest,
    service: ClaimComparisonServiceDep,
    settings: SettingsDep,
) -> ClaimComparisonResponse:
    outcome = await service.compare(
        target_document_id=request.target_document_id,
        target_claim_number=request.target_claim_number,
        reference_document_id=request.reference_document_id,
        mode=request.mode,
        top_k=min(request.top_k, settings.search_top_k_max),
    )
    return _comparison_response(outcome, rrf_k=settings.rrf_k)


def _comparison_response(outcome: ClaimComparisonOutcome, *, rrf_k: int) -> ClaimComparisonResponse:
    profile = outcome.profile
    target = outcome.target
    return ClaimComparisonResponse(
        target=ComparisonClaimResponse(
            document_id=target.document_id,
            claim_number=target.claim_number,
            claim_type=target.claim_type,
            text=target.text,
            depends_on=target.depends_on,
            source_spans=[
                SourceLocator(
                    document_id=target.document_id,
                    page_number=span.page_number,
                    start_char=span.start_char,
                    end_char=span.end_char,
                )
                for span in target.spans
            ],
        ),
        reference_document_id=outcome.reference_document_id,
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
        searched_index_run_count=outcome.searched_index_run_count,
        no_correspondence_found=not outcome.matches,
        no_correspondence_reason=outcome.no_correspondence_reason,
        match_count=len(outcome.matches),
        matches=[
            ComparisonMatchResponse(
                document_id=result.document_id,
                claim_number=result.claim_number,
                claim_type=result.claim_type,
                text=result.text,
                depends_on=result.depends_on,
                source_spans=[
                    SourceLocator(
                        document_id=result.document_id,
                        page_number=span.page_number,
                        start_char=span.start_char,
                        end_char=span.end_char,
                    )
                    for span in result.spans
                ],
                dense_rank=result.dense_rank,
                dense_score=result.dense_score,
                lexical_rank=result.lexical_rank,
                lexical_score=result.lexical_score,
                fused_rank=result.fused_rank,
                fused_score=result.fused_score,
            )
            for result in outcome.matches
        ],
    )
