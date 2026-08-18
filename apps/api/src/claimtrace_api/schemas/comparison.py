"""Request and response models for bounded claim-to-claim comparison.

Comparison is deliberately narrower than a general semantic-analysis endpoint:
one stored target claim is used as the retrieval query and candidates are searched
only inside one caller-selected reference document. The response describes textual
correspondence and provenance only; there is no field for a legal conclusion.
"""

from __future__ import annotations

import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from claimtrace_api.db.models import ClaimType
from claimtrace_api.retrieval.base import RetrievalMode
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.schemas.retrieval import MAX_TOP_K, RetrievalProfileResponse


class ClaimComparisonRequest(BaseModel):
    """Compare one target claim against claims in one reference document."""

    model_config = ConfigDict(extra="forbid")

    target_document_id: uuid.UUID
    target_claim_number: int = Field(ge=1)
    reference_document_id: uuid.UUID
    mode: RetrievalMode = RetrievalMode.HYBRID
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)

    @model_validator(mode="after")
    def _require_distinct_documents(self) -> Self:
        if self.target_document_id == self.reference_document_id:
            raise ValueError("target and reference documents must be different")
        return self


class ComparisonClaimResponse(BaseModel):
    """Stored claim text with canonical source coordinates from the same document."""

    document_id: uuid.UUID
    claim_number: int
    claim_type: ClaimType
    text: str
    depends_on: list[int] = Field(default_factory=list)
    source_spans: list[SourceLocator] = Field(min_length=1)

    @model_validator(mode="after")
    def _require_source_span_document_identity(self) -> Self:
        if any(span.document_id != self.document_id for span in self.source_spans):
            raise ValueError("all claim source spans must belong to the claim document")
        return self


class ComparisonMatchResponse(ComparisonClaimResponse):
    """One reference-document claim returned by the existing retrieval stack."""

    dense_rank: int | None = None
    dense_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    fused_rank: int
    fused_score: float


class ClaimComparisonResponse(BaseModel):
    """A bounded textual comparison result.

    ``no_correspondence_found`` means retrieval returned no claims from the selected
    reference document. It is not a legal statement about novelty, equivalence,
    infringement, validity, or patentability.

    The response also owns the final representation-level invariants. The service
    already refuses a retrieval scope leak, but enforcing the same rule here keeps a
    future alternate caller or mapper from serialising contradictory provenance or
    no-correspondence state.
    """

    target: ComparisonClaimResponse
    reference_document_id: uuid.UUID
    mode: RetrievalMode
    profile: RetrievalProfileResponse
    searched_index_run_count: int = Field(ge=0)
    no_correspondence_found: bool
    no_correspondence_reason: Literal["reference_not_indexed", "no_matches"] | None = None
    match_count: int = Field(ge=0)
    matches: list[ComparisonMatchResponse] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_coherent_comparison_state(self) -> Self:
        if self.target.document_id == self.reference_document_id:
            raise ValueError("target and reference documents must be different")

        if any(match.document_id != self.reference_document_id for match in self.matches):
            raise ValueError("all comparison matches must belong to the reference document")

        if self.match_count != len(self.matches):
            raise ValueError("match_count must equal the number of matches")

        has_matches = bool(self.matches)
        if self.no_correspondence_found == has_matches:
            raise ValueError("no_correspondence_found must be true exactly when matches are empty")

        if has_matches:
            if self.no_correspondence_reason is not None:
                raise ValueError("no_correspondence_reason must be null when matches exist")
            return self

        if self.no_correspondence_reason is None:
            raise ValueError("empty comparison results require a no_correspondence_reason")

        if self.no_correspondence_reason == "reference_not_indexed":
            if self.searched_index_run_count != 0:
                raise ValueError("reference_not_indexed requires zero searched index runs")
        elif self.searched_index_run_count == 0:
            raise ValueError("no_matches requires at least one searched index run")

        return self
