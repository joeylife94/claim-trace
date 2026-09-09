"""D4 description evidence request and response models."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from claimtrace_api.retrieval.base import RetrievalMode
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.schemas.retrieval import (
    MAX_CANDIDATE_COUNT,
    MAX_DOCUMENT_FILTER,
    MAX_QUERY_LENGTH,
    MAX_TOP_K,
    RetrievalProfileResponse,
)


class DescriptionSegmentResponse(BaseModel):
    id: uuid.UUID
    evidence_kind: Literal["description"] = "description"
    segment_index: int
    section_heading: str | None = None
    text: str
    source_span: SourceLocator
    source_url: str


class DescriptionDerivationResponse(BaseModel):
    run_id: uuid.UUID
    status: Literal["completed", "unsupported"]
    segmenter_name: str
    segmenter_version: str
    segment_count: int
    warnings: list[str] = Field(default_factory=list)
    created: bool
    segments: list[DescriptionSegmentResponse] = Field(default_factory=list)


class DescriptionIndexResponse(BaseModel):
    status: Literal["completed", "unsupported"]
    profile: RetrievalProfileResponse
    indexed_segment_count: int
    warnings: list[str] = Field(default_factory=list)
    created: bool


class DescriptionSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    mode: RetrievalMode = RetrievalMode.HYBRID
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_DOCUMENT_FILTER)
    top_k: int = Field(default=10, ge=1, le=MAX_TOP_K)
    dense_candidate_count: int = Field(default=30, ge=1, le=MAX_CANDIDATE_COUNT)
    lexical_candidate_count: int = Field(default=30, ge=1, le=MAX_CANDIDATE_COUNT)

    @field_validator("query")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class DescriptionSearchResultResponse(DescriptionSegmentResponse):
    document_id: uuid.UUID
    document_filename: str
    dense_rank: int | None = None
    dense_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    fused_rank: int
    fused_score: float


class DescriptionSearchResponse(BaseModel):
    mode: RetrievalMode
    profile: RetrievalProfileResponse
    dense_candidate_count: int
    lexical_candidate_count: int
    result_count: int
    results: list[DescriptionSearchResultResponse] = Field(default_factory=list)
