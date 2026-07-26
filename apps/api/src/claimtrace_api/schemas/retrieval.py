"""Request/response models for claim indexing and hybrid retrieval.

Bounds live on the request models rather than in the handlers, so an oversized
``top_k`` or an empty query is rejected by FastAPI's validation with a 422 before
any database or model work starts.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from claimtrace_api.db.models import ClaimIndexStatus, ClaimType
from claimtrace_api.retrieval.base import RetrievalMode
from claimtrace_api.schemas.locators import SourceLocator

#: Hard ceilings, mirrored in Settings defaults. Declared as literals because a
#: Pydantic field constraint has to be resolvable at class-definition time; the
#: matching settings let an operator lower them, never raise them.
MAX_QUERY_LENGTH = 512
MAX_TOP_K = 50
MAX_CANDIDATE_COUNT = 200
MAX_DOCUMENT_FILTER = 50


class ClaimIndexRunResponse(BaseModel):
    """Metadata for one indexing pass over one claim parse result."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_parse_result_id: uuid.UUID
    status: ClaimIndexStatus

    embedding_provider: str
    embedding_model: str
    embedding_model_version: str
    embedding_dimension: int
    vectors_normalized: bool
    normalization_version: str
    lexical_strategy: str
    lexical_strategy_version: str

    indexed_claim_count: int

    #: Safe to surface: these are the application's own stable codes and
    #: user-facing sentences, never a traceback or a cache path.
    error_code: str | None = None
    error_message: str | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RetrievalProfileResponse(BaseModel):
    """The profile a search was executed against.

    Returned with every search so a result set is interpretable on its own: two
    runs of the same query against different models are different experiments,
    and the response says which one this was.
    """

    embedding_provider: str
    embedding_model: str
    embedding_model_version: str
    embedding_dimension: int
    vectors_normalized: bool
    normalization_version: str
    lexical_strategy: str
    lexical_strategy_version: str
    rrf_k: int


class ClaimSearchRequest(BaseModel):
    """A claim search."""

    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    mode: RetrievalMode = RetrievalMode.HYBRID
    #: Absent or empty means every indexed document.
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_DOCUMENT_FILTER)
    top_k: int = Field(default=10, ge=1, le=MAX_TOP_K)
    dense_candidate_count: int = Field(default=30, ge=1, le=MAX_CANDIDATE_COUNT)
    lexical_candidate_count: int = Field(default=30, ge=1, le=MAX_CANDIDATE_COUNT)

    @field_validator("query")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """A whitespace-only query passes min_length but retrieves nothing."""
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class ClaimSearchResultResponse(BaseModel):
    """One retrieved claim, with its provenance and per-channel ranking.

    Every ranking field is nullable except the fused pair, and that is
    meaningful rather than incidental: ``dense_rank`` is null when the dense
    channel did not retrieve this claim, which is information a reader debugging
    a query needs. Clients must render the absence, not coerce it to zero.
    """

    document_id: uuid.UUID
    document_filename: str
    claim_number: int
    claim_type: ClaimType
    #: The original stored claim text, never the normalised search form.
    text: str
    depends_on: list[int] = Field(default_factory=list)
    #: The canonical source coordinates, identical to what the claim endpoints
    #: return. Retrieval refines how a claim is *found*; it never changes where
    #: the claim *is*.
    source_spans: list[SourceLocator]

    dense_rank: int | None = None
    dense_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    fused_rank: int
    fused_score: float


class ClaimSearchResponse(BaseModel):
    """A search result set, with everything needed to interpret it."""

    mode: RetrievalMode
    profile: RetrievalProfileResponse
    #: Completed index runs the active profile matched. Zero means nothing has
    #: been indexed for this profile - distinct from a query that matched nothing.
    searched_index_run_count: int
    dense_candidate_count: int
    lexical_candidate_count: int
    result_count: int
    results: list[ClaimSearchResultResponse] = Field(default_factory=list)
