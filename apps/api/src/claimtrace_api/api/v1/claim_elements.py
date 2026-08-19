"""Source-backed deterministic claim-element decomposition endpoint."""

from __future__ import annotations

import uuid
from http import HTTPStatus

from fastapi import APIRouter, Response

from claimtrace_api.api.deps import (
    ClaimElementServiceDep,
    ClaimParsingServiceDep,
    SessionDep,
)
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.element_models import ElementDecompositionRun
from claimtrace_api.db.models import ClaimParseStatus, Document
from claimtrace_api.schemas.claim_elements import (
    ClaimElementResponse,
    ClaimElementSpanResponse,
    ElementDecompositionResponse,
    ElementWarningResponse,
)
from claimtrace_api.schemas.errors import ApiErrorResponse
from claimtrace_api.schemas.locators import SourceLocator

router = APIRouter(
    prefix="/documents/{document_id}/claims/{claim_number}/elements",
    tags=["claim-elements"],
)

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    HTTPStatus.NOT_FOUND: {"model": ApiErrorResponse},
    HTTPStatus.CONFLICT: {"model": ApiErrorResponse},
    HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ApiErrorResponse},
}


@router.post(
    "/decompose",
    response_model=ElementDecompositionResponse,
    status_code=HTTPStatus.CREATED,
    summary="Decompose one persisted claim into source-backed elements",
    description=(
        "Runs the deterministic element parser over one persisted claim and stores "
        "the result by parser version. Repeating the same request returns the "
        "existing run with 200 instead of duplicating it. Elements and warnings are "
        "machine-produced review material, not legal conclusions."
    ),
    responses={HTTPStatus.OK: {"model": ElementDecompositionResponse}, **_ERROR_RESPONSES},
)
async def decompose_claim_elements(
    document_id: uuid.UUID,
    claim_number: int,
    response: Response,
    session: SessionDep,
    parsing: ClaimParsingServiceDep,
    service: ClaimElementServiceDep,
) -> ElementDecompositionResponse:
    document = await session.get(Document, document_id)
    if document is None:
        raise AppError(ErrorCode.DOCUMENT_NOT_FOUND, "Document not found.")

    snapshot = await parsing.snapshot(document_id)
    if snapshot is None:
        raise AppError(
            ErrorCode.CLAIM_PARSE_NOT_FOUND,
            "This document has not been parsed for claims yet.",
        )
    if snapshot.result.status is not ClaimParseStatus.COMPLETED:
        raise AppError(
            ErrorCode.CLAIM_PARSE_NOT_COMPLETED,
            "Claim element decomposition requires a completed claim parse result.",
        )

    claim = next(
        (item for item in snapshot.claims if item.claim_number == claim_number),
        None,
    )
    if claim is None:
        raise AppError(ErrorCode.CLAIM_NOT_FOUND, f"Claim {claim_number} is not in this document.")

    outcome = await service.decompose(claim.id)
    if not outcome.created:
        response.status_code = HTTPStatus.OK

    return _response(outcome.run, document_id=document_id)


def _response(
    run: ElementDecompositionRun,
    *,
    document_id: uuid.UUID,
) -> ElementDecompositionResponse:
    elements = sorted(run.elements, key=lambda element: element.sequence_number)
    return ElementDecompositionResponse(
        id=run.id,
        claim_id=run.claim_id,
        parser_name=run.parser_name,
        parser_version=run.parser_version,
        element_count=run.element_count,
        warning_count=run.warning_count,
        warnings=[ElementWarningResponse.model_validate(item) for item in run.warnings],
        elements=[
            ClaimElementResponse(
                id=element.id,
                sequence_number=element.sequence_number,
                text=element.text,
                spans=[
                    ClaimElementSpanResponse(
                        sequence_number=span.sequence_number,
                        page_number=span.page_number,
                        start_char=span.start_char,
                        end_char=span.end_char,
                        locator=SourceLocator(
                            document_id=document_id,
                            page_number=span.page_number,
                            start_char=span.start_char,
                            end_char=span.end_char,
                        ),
                    )
                    for span in sorted(element.spans, key=lambda item: item.sequence_number)
                ],
            )
            for element in elements
        ],
        created_at=run.created_at,
    )
