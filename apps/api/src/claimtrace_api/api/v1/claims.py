"""Claim structural parsing endpoints, nested under a document."""

from __future__ import annotations

import uuid
from http import HTTPStatus

from fastapi import APIRouter, Response

from claimtrace_api.api.deps import ClaimIndexingServiceDep, ClaimParsingServiceDep, SessionDep
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import Claim, ClaimParseResult, Document
from claimtrace_api.schemas.claims import (
    ClaimDetailResponse,
    ClaimParseResultResponse,
    ClaimResponse,
    ClaimSetResponse,
    ClaimSpanResponse,
    ParseWarningResponse,
)
from claimtrace_api.schemas.errors import ApiErrorResponse
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.schemas.retrieval import ClaimIndexRunResponse
from claimtrace_api.services.claim_parsing import ClaimSetSnapshot

router = APIRouter(prefix="/documents/{document_id}/claims", tags=["claims"])

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    HTTPStatus.NOT_FOUND: {"model": ApiErrorResponse},
    HTTPStatus.CONFLICT: {"model": ApiErrorResponse},
    HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ApiErrorResponse},
}


@router.post(
    "/parse",
    response_model=ClaimSetResponse,
    status_code=HTTPStatus.CREATED,
    summary="Parse claim structure",
    description=(
        "Runs deterministic claim structural parsing over the document's stored "
        "page text.\n\n"
        "Returns 201 for a new result and 200 when a result for the same parser "
        "version already exists. A document with no detectable claims completes "
        "with status `no_claims_found`; that is an outcome, not an error. "
        "Document ingestion status is never modified by this endpoint."
    ),
    responses={HTTPStatus.OK: {"model": ClaimSetResponse}, **_ERROR_RESPONSES},
)
async def parse_claims(
    document_id: uuid.UUID,
    response: Response,
    session: SessionDep,
    service: ClaimParsingServiceDep,
) -> ClaimSetResponse:
    document = await _require_document(document_id, session)

    outcome = await service.parse(document)
    if not outcome.created:
        response.status_code = HTTPStatus.OK

    snapshot = await service.snapshot(document_id)
    if snapshot is None:  # pragma: no cover - the parse just wrote one
        raise AppError(ErrorCode.CLAIM_PARSE_NOT_FOUND, "No claim parse result was found.")
    return _claim_set(snapshot)


@router.get(
    "",
    response_model=ClaimSetResponse,
    summary="Get parsed claims",
    description=(
        "The current parse result with its ordered claims, dependency references, and source spans."
    ),
    responses=_ERROR_RESPONSES,
)
async def get_claims(
    document_id: uuid.UUID, session: SessionDep, service: ClaimParsingServiceDep
) -> ClaimSetResponse:
    await _require_document(document_id, session)
    snapshot = await service.snapshot(document_id)
    if snapshot is None:
        raise AppError(
            ErrorCode.CLAIM_PARSE_NOT_FOUND,
            "This document has not been parsed for claims yet.",
        )
    return _claim_set(snapshot)


#: Declared before "/{claim_number}": FastAPI matches in declaration order, and
#: the reverse would send a request for /index into the int path parameter.
@router.post(
    "/index",
    response_model=ClaimIndexRunResponse,
    status_code=HTTPStatus.CREATED,
    summary="Index claims for retrieval",
    description=(
        "Embeds this document's parsed claims and writes their search records.\n\n"
        "Returns 201 for a newly completed run and 200 when a completed run for the "
        "same retrieval profile already exists - the profile being the embedding "
        "provider, model, model version, dimension, normalisation policy, and "
        "lexical strategy. A failed or stranded run for the same profile is retried "
        "in place. Neither document ingestion status nor claim parsing status is "
        "modified by this endpoint."
    ),
    responses={
        HTTPStatus.OK: {"model": ClaimIndexRunResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
        **_ERROR_RESPONSES,
    },
)
async def index_claims(
    document_id: uuid.UUID,
    response: Response,
    session: SessionDep,
    service: ClaimIndexingServiceDep,
) -> ClaimIndexRunResponse:
    document = await _require_document(document_id, session)

    outcome = await service.index(document)
    if not outcome.created:
        response.status_code = HTTPStatus.OK

    return ClaimIndexRunResponse.model_validate(outcome.run)


@router.get(
    "/index",
    response_model=ClaimIndexRunResponse,
    summary="Get claim index status",
    description=(
        "The most recent index run for this document, whatever retrieval profile "
        "it was built with. A run built by a model the deployment has since moved "
        "away from is still reported, rather than the document appearing unindexed."
    ),
    responses=_ERROR_RESPONSES,
)
async def get_claim_index(
    document_id: uuid.UUID,
    session: SessionDep,
    service: ClaimIndexingServiceDep,
) -> ClaimIndexRunResponse:
    await _require_document(document_id, session)

    run = await service.current_run(document_id)
    if run is None:
        raise AppError(
            ErrorCode.CLAIM_INDEX_NOT_FOUND,
            "This document's claims have not been indexed yet.",
        )
    return ClaimIndexRunResponse.model_validate(run)


@router.get(
    "/{claim_number}",
    response_model=ClaimDetailResponse,
    summary="Get one claim",
    responses=_ERROR_RESPONSES,
)
async def get_claim(
    document_id: uuid.UUID,
    claim_number: int,
    session: SessionDep,
    service: ClaimParsingServiceDep,
) -> ClaimDetailResponse:
    await _require_document(document_id, session)
    snapshot = await service.snapshot(document_id)
    if snapshot is None:
        raise AppError(
            ErrorCode.CLAIM_PARSE_NOT_FOUND,
            "This document has not been parsed for claims yet.",
        )

    for claim in snapshot.claims:
        if claim.claim_number == claim_number:
            return ClaimDetailResponse(
                result=_result_response(snapshot.result),
                claim=_claim_response(
                    claim, snapshot.dependencies.get(claim.id, []), snapshot.result.document_id
                ),
            )

    raise AppError(ErrorCode.CLAIM_NOT_FOUND, f"Claim {claim_number} is not in this document.")


# -- mapping ---------------------------------------------------------------


def _claim_set(snapshot: ClaimSetSnapshot) -> ClaimSetResponse:
    return ClaimSetResponse(
        result=_result_response(snapshot.result),
        claims=[
            _claim_response(
                claim, snapshot.dependencies.get(claim.id, []), snapshot.result.document_id
            )
            for claim in snapshot.claims
        ],
    )


def _result_response(result: ClaimParseResult) -> ClaimParseResultResponse:
    return ClaimParseResultResponse(
        id=result.id,
        document_id=result.document_id,
        status=result.status,
        parser_name=result.parser_name,
        parser_version=result.parser_version,
        claim_count=result.claim_count,
        warning_count=result.warning_count,
        warnings=[ParseWarningResponse.model_validate(item) for item in result.warnings],
        error_code=result.error_code,
        error_message=result.error_message,
        started_at=result.started_at,
        completed_at=result.completed_at,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


def _claim_response(claim: Claim, depends_on: list[int], document_id: uuid.UUID) -> ClaimResponse:
    spans = sorted(claim.spans, key=lambda span: span.sequence_number)
    return ClaimResponse(
        claim_number=claim.claim_number,
        claim_type=claim.claim_type,
        text=claim.text,
        depends_on=depends_on,
        spans=[
            ClaimSpanResponse(
                sequence_number=span.sequence_number,
                page_number=span.page_number,
                start_char=span.start_char,
                end_char=span.end_char,
                # The same coordinate the page endpoint uses, so a client can
                # resolve a claim's source without a second lookup.
                locator=SourceLocator(
                    document_id=document_id,
                    page_number=span.page_number,
                    start_char=span.start_char,
                    end_char=span.end_char,
                ),
            )
            for span in spans
        ],
        crosses_pages=len({span.page_number for span in spans}) > 1,
    )


async def _require_document(document_id: uuid.UUID, session: SessionDep) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise AppError(ErrorCode.DOCUMENT_NOT_FOUND, "Document not found.")
    return document
