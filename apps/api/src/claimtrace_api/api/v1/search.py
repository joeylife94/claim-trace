"""Claim search endpoints.

A POST rather than a GET with query parameters. Two reasons, and the second is
the one that decides it: the request has structure (a mode, a document filter, three
independent limits) that does not flatten into a query string cleanly, and a
patent search query is confidential - a GET would put it in the URL, where it
lands in access logs, proxy logs, and browser history by default.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter

from claimtrace_api.api.deps import ClaimSearchServiceDep, SettingsDep
from claimtrace_api.schemas.errors import ApiErrorResponse
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.schemas.retrieval import (
    ClaimSearchRequest,
    ClaimSearchResponse,
    ClaimSearchResultResponse,
    RetrievalProfileResponse,
)
from claimtrace_api.services.claim_search import SearchOutcome

router = APIRouter(prefix="/search", tags=["search"])


@router.post(
    "/claims",
    response_model=ClaimSearchResponse,
    summary="Search claims",
    description=(
        "Hybrid retrieval over indexed claims.\n\n"
        "`hybrid` (the default) retrieves dense and lexical candidates independently "
        "and fuses them with Reciprocal Rank Fusion; `dense` and `lexical` use one "
        "channel each. Only index runs matching the active retrieval profile are "
        "searched, so embeddings from different models are never mixed.\n\n"
        "Every result carries the canonical source spans "
        "`(document_id, page_number, start_char, end_char)`, so each one can be "
        "resolved against the stored page text it came from."
    ),
    responses={
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ApiErrorResponse},
    },
)
async def search_claims(
    request: ClaimSearchRequest,
    service: ClaimSearchServiceDep,
    settings: SettingsDep,
) -> ClaimSearchResponse:
    outcome = await service.search(
        query=request.query,
        mode=request.mode,
        document_ids=request.document_ids or None,
        # The request model's ceilings are absolute; these settings let an
        # operator lower them further without a redeploy of the schema.
        top_k=min(request.top_k, settings.search_top_k_max),
        dense_candidate_count=min(
            request.dense_candidate_count, settings.search_candidate_count_max
        ),
        lexical_candidate_count=min(
            request.lexical_candidate_count, settings.search_candidate_count_max
        ),
    )
    return _search_response(outcome, rrf_k=settings.rrf_k)


def _search_response(outcome: SearchOutcome, *, rrf_k: int) -> ClaimSearchResponse:
    return ClaimSearchResponse(
        mode=outcome.mode,
        profile=RetrievalProfileResponse(
            embedding_provider=outcome.profile.embedding_provider,
            embedding_model=outcome.profile.embedding_model,
            embedding_model_version=outcome.profile.embedding_model_version,
            embedding_dimension=outcome.profile.embedding_dimension,
            vectors_normalized=outcome.profile.vectors_normalized,
            normalization_version=outcome.profile.normalization_version,
            lexical_strategy=outcome.profile.lexical_strategy,
            lexical_strategy_version=outcome.profile.lexical_strategy_version,
            rrf_k=rrf_k,
        ),
        searched_index_run_count=outcome.searched_index_run_count,
        dense_candidate_count=outcome.dense_candidate_count,
        lexical_candidate_count=outcome.lexical_candidate_count,
        result_count=len(outcome.results),
        results=[
            ClaimSearchResultResponse(
                document_id=result.document_id,
                document_filename=result.document_filename,
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
            for result in outcome.results
        ],
    )
