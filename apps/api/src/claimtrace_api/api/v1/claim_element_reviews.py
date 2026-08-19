"""Append-only human review endpoints for exact decomposition runs."""

from __future__ import annotations

import uuid
from http import HTTPStatus

from fastapi import APIRouter

from claimtrace_api.api.deps import ClaimElementReviewServiceDep
from claimtrace_api.schemas.claim_element_reviews import (
    CreateElementReviewRequest,
    ElementReviewResponse,
    ElementReviewSnapshotResponse,
)
from claimtrace_api.schemas.claim_elements import ClaimElementResponse, ClaimElementSpanResponse
from claimtrace_api.schemas.errors import ApiErrorResponse
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.services.claim_element_reviews import ReviewRunSnapshot

router = APIRouter(prefix="/element-decomposition-runs/{run_id}/reviews", tags=["claim-elements"])

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    HTTPStatus.NOT_FOUND: {"model": ApiErrorResponse},
}


@router.post(
    "",
    response_model=ElementReviewSnapshotResponse,
    status_code=HTTPStatus.CREATED,
    responses=_ERROR_RESPONSES,
    summary="Record a human review of one exact decomposition run",
    description=(
        "Appends an accepted or needs-correction judgement without changing the "
        "machine decomposition. Review history remains attached to this exact parser run."
    ),
)
async def create_element_review(
    run_id: uuid.UUID,
    payload: CreateElementReviewRequest,
    service: ClaimElementReviewServiceDep,
) -> ElementReviewSnapshotResponse:
    snapshot = await service.add_review(run_id=run_id, status=payload.status)
    return _response(snapshot)


@router.get(
    "",
    response_model=ElementReviewSnapshotResponse,
    responses={HTTPStatus.NOT_FOUND: {"model": ApiErrorResponse}},
    summary="Read human review history for one exact decomposition run",
)
async def get_element_reviews(
    run_id: uuid.UUID,
    service: ClaimElementReviewServiceDep,
) -> ElementReviewSnapshotResponse:
    return _response(await service.snapshot(run_id))


def _response(snapshot: ReviewRunSnapshot) -> ElementReviewSnapshotResponse:
    run = snapshot.run
    return ElementReviewSnapshotResponse(
        run_id=run.id,
        claim_id=run.claim_id,
        document_id=snapshot.document_id,
        parser_name=run.parser_name,
        parser_version=run.parser_version,
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
                            document_id=snapshot.document_id,
                            page_number=span.page_number,
                            start_char=span.start_char,
                            end_char=span.end_char,
                        ),
                    )
                    for span in sorted(element.spans, key=lambda item: item.sequence_number)
                ],
            )
            for element in sorted(run.elements, key=lambda item: item.sequence_number)
        ],
        reviews=[
            ElementReviewResponse(
                id=review.id,
                status=review.status,
                created_at=review.created_at,
            )
            for review in snapshot.reviews
        ],
    )
