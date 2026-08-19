"""Append-only human review service for exact decomposition runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.element_models import ClaimElement, ElementDecompositionRun
from claimtrace_api.db.models import Claim, ClaimParseResult
from claimtrace_api.db.review_models import (
    DecompositionReviewStatus,
    ElementDecompositionReview,
)


@dataclass(frozen=True, slots=True)
class ReviewRunSnapshot:
    """Review history plus the exact source-backed machine run it judges."""

    run: ElementDecompositionRun
    document_id: uuid.UUID
    reviews: tuple[ElementDecompositionReview, ...]


class ClaimElementReviewService:
    """Persist immutable review actions without mutating machine decomposition."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def add_review(
        self,
        *,
        run_id: uuid.UUID,
        status: DecompositionReviewStatus,
    ) -> ReviewRunSnapshot:
        run = await self._require_run(run_id)
        review = ElementDecompositionReview(
            id=uuid.uuid4(),
            run_id=run.id,
            status=status.value,
        )
        self._session.add(review)
        await self._session.commit()
        return await self.snapshot(run_id)

    async def snapshot(self, run_id: uuid.UUID) -> ReviewRunSnapshot:
        run = await self._require_run(run_id)
        document_id = await self._document_id(run.claim_id)
        reviews = (
            (
                await self._session.execute(
                    select(ElementDecompositionReview)
                    .where(ElementDecompositionReview.run_id == run_id)
                    .order_by(
                        ElementDecompositionReview.created_at,
                        ElementDecompositionReview.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return ReviewRunSnapshot(
            run=run,
            document_id=document_id,
            reviews=tuple(reviews),
        )

    async def _require_run(self, run_id: uuid.UUID) -> ElementDecompositionRun:
        statement = (
            select(ElementDecompositionRun)
            .where(ElementDecompositionRun.id == run_id)
            .options(
                selectinload(ElementDecompositionRun.elements).selectinload(ClaimElement.spans)
            )
        )
        run = (await self._session.execute(statement)).scalars().first()
        if run is None:
            raise AppError(
                ErrorCode.ELEMENT_DECOMPOSITION_RUN_NOT_FOUND,
                "Element decomposition run not found.",
            )
        return run

    async def _document_id(self, claim_id: uuid.UUID) -> uuid.UUID:
        statement = (
            select(ClaimParseResult.document_id)
            .join(Claim, Claim.parse_result_id == ClaimParseResult.id)
            .where(Claim.id == claim_id)
        )
        document_id = (await self._session.execute(statement)).scalar_one()
        return document_id
