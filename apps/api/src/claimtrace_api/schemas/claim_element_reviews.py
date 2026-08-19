"""Public contract for append-only human review of decomposition runs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from claimtrace_api.db.review_models import DecompositionReviewStatus
from claimtrace_api.schemas.claim_elements import ClaimElementResponse


class CreateElementReviewRequest(BaseModel):
    """One bounded reviewer judgement; model validation rejects any other state."""

    model_config = ConfigDict(extra="forbid")

    status: DecompositionReviewStatus


class ElementReviewResponse(BaseModel):
    id: uuid.UUID
    status: DecompositionReviewStatus
    created_at: datetime


class ElementReviewSnapshotResponse(BaseModel):
    """Review history attached to the exact machine run and evidence reviewed."""

    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    claim_id: uuid.UUID
    document_id: uuid.UUID
    parser_name: str
    parser_version: str
    elements: list[ClaimElementResponse]
    reviews: list[ElementReviewResponse]
