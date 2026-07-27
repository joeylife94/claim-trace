"""Evidence-grounded answering.

One endpoint. There is deliberately no companion diagnostics route that returns
the prompt, the raw draft, or the catalog: a second surface exposing what the
first one refuses to expose would make the refusal decorative, and everything
worth inspecting during development is reachable through the service's unit
tests and its structured log line.

A POST for the same two reasons claim search is one, and the second decides it:
the request has structure that does not flatten into a query string, and a
question about unpublished patent work is confidential - a GET would put it in
access logs, proxy logs, and browser history by default.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter

from claimtrace_api.api.deps import GroundedGenerationServiceDep, SettingsDep
from claimtrace_api.schemas.errors import ApiErrorResponse
from claimtrace_api.schemas.grounded import (
    GroundedAnswerRequest,
    GroundedAnswerResponse,
    GroundedEvidenceResponse,
    GroundedRetrievalResponse,
    GroundedSourceSpanResponse,
    GroundedStatementResponse,
)
from claimtrace_api.schemas.llm import GenerationMetadataResponse, TokenUsageResponse
from claimtrace_api.schemas.retrieval import RetrievalProfileResponse
from claimtrace_api.services.grounded_generation import GroundedAnswer

router = APIRouter(prefix="/grounded", tags=["grounded"])


@router.post(
    "/answers",
    response_model=GroundedAnswerResponse,
    summary="Answer a question from indexed claim text",
    description=(
        "Retrieves claims with the Phase 3A hybrid search, asks the configured local "
        "model to answer from those claims alone, and returns only statements whose "
        "citations resolve to stored source text.\n\n"
        "The model never sees and never produces a document id, a page number, or a "
        "character offset. It selects from opaque evidence identifiers issued by the "
        "server for this request; the server resolves them back to the canonical "
        "`(document_id, page_number, start_char, end_char)` spans and reads each quote "
        "out of the stored page text.\n\n"
        "`insufficient_evidence: true` is a normal 200 response. It means the retrieved "
        "claims do not answer the question, and it is returned in preference to a "
        "plausible answer that nothing supports.\n\n"
        "A resolvable citation shows that a statement points at retrieved source text. "
        "It is not a proof that the cited text entails the statement, and this endpoint "
        "reaches no legal conclusion of any kind."
    ),
    responses={
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ApiErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
        HTTPStatus.GATEWAY_TIMEOUT: {"model": ApiErrorResponse},
        HTTPStatus.BAD_GATEWAY: {"model": ApiErrorResponse},
    },
)
async def grounded_answer(
    request: GroundedAnswerRequest,
    service: GroundedGenerationServiceDep,
    settings: SettingsDep,
) -> GroundedAnswerResponse:
    answer = await service.answer(
        query=request.query,
        mode=request.mode,
        document_ids=request.document_ids or None,
        # The schema's ceiling is absolute; this lets an operator lower it
        # further without redeploying a schema.
        top_k=min(request.top_k, settings.search_top_k_max),
    )
    return _answer_response(answer, rrf_k=settings.rrf_k)


def _answer_response(answer: GroundedAnswer, *, rrf_k: int) -> GroundedAnswerResponse:
    retrieval = answer.retrieval
    return GroundedAnswerResponse(
        answer=answer.answer,
        statements=[
            GroundedStatementResponse(
                text=statement.text, evidence_ids=list(statement.evidence_ids)
            )
            for statement in answer.statements
        ],
        evidence=[
            GroundedEvidenceResponse(
                evidence_id=evidence.entry.evidence_id,
                document_id=evidence.entry.candidate.document_id,
                document_name=evidence.entry.candidate.document_name,
                claim_number=evidence.entry.candidate.claim_number,
                claim_type=evidence.entry.candidate.claim_type,
                depends_on=list(evidence.entry.candidate.depends_on),
                source_spans=[
                    GroundedSourceSpanResponse(locator=span.locator, quote=span.quote)
                    for span in evidence.spans
                ],
                crosses_pages=evidence.entry.candidate.crosses_pages,
                fused_rank=evidence.entry.candidate.fused_rank,
                fused_score=evidence.entry.candidate.fused_score,
                dense_rank=evidence.entry.candidate.dense_rank,
                dense_score=evidence.entry.candidate.dense_score,
                lexical_rank=evidence.entry.candidate.lexical_rank,
                lexical_score=evidence.entry.candidate.lexical_score,
            )
            for evidence in answer.evidence
        ],
        insufficient_evidence=answer.insufficient_evidence,
        insufficient_reason=answer.insufficient_reason,
        retrieval=GroundedRetrievalResponse(
            mode=retrieval.mode,
            profile=RetrievalProfileResponse(
                embedding_provider=retrieval.profile.embedding_provider,
                embedding_model=retrieval.profile.embedding_model,
                embedding_model_version=retrieval.profile.embedding_model_version,
                embedding_dimension=retrieval.profile.embedding_dimension,
                vectors_normalized=retrieval.profile.vectors_normalized,
                normalization_version=retrieval.profile.normalization_version,
                lexical_strategy=retrieval.profile.lexical_strategy,
                lexical_strategy_version=retrieval.profile.lexical_strategy_version,
                rrf_k=rrf_k,
            ),
            searched_index_run_count=retrieval.searched_index_run_count,
            retrieved_candidate_count=retrieval.retrieved_candidate_count,
            included_evidence_count=retrieval.included_evidence_count,
            omitted_evidence_count=retrieval.omitted_evidence_count,
        ),
        generation=_generation_metadata(answer),
        warnings=list(answer.warnings),
    )


def _generation_metadata(answer: GroundedAnswer) -> GenerationMetadataResponse | None:
    """Reuses the diagnostics metadata shape, because it is the same fact.

    Null when no provider was contacted. A zero-filled block would report a
    generation that never happened, and a client rendering "0 tokens, 0.0s"
    cannot tell that from a very fast one.
    """
    response = answer.generation
    if response is None:
        return None
    return GenerationMetadataResponse(
        provider=response.provider,
        model=response.model,
        model_version=response.model_version,
        finish_reason=response.finish_reason.value,
        usage=TokenUsageResponse(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
        ),
        duration_seconds=round(response.duration_seconds, 4),
        attempts=response.attempts,
        structured_output_mode=(
            response.structured_output_mode.value if response.structured_output_mode else None
        ),
        warnings=list(response.warnings),
    )
