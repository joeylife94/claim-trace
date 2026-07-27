"""Request and response models for evidence-grounded answering.

The request model is mostly interesting for what it refuses. ``extra="forbid"``
is not tidiness here: it is the enforcement point for the rule that a caller
controls the *question*, never the machinery. A body carrying ``model``,
``provider``, ``system``, ``temperature``, ``seed``, ``schema``,
``evidence_ids``, ``page_number``, or ``context`` is rejected with a 422 rather
than silently ignored - and silently ignoring it would be worse, because a
client could ship code that appears to pin a model for a year before anyone
notices it never did.

The response is entirely server-owned. Every field in it is either something the
server computed, something it retrieved, or something a model said that survived
citation validation. There is no field into which unvalidated model text can
reach a reader.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from claimtrace_api.db.models import ClaimType
from claimtrace_api.grounding.draft import InsufficientReason
from claimtrace_api.retrieval.base import RetrievalMode
from claimtrace_api.schemas.llm import GenerationMetadataResponse
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.schemas.retrieval import (
    MAX_DOCUMENT_FILTER,
    MAX_QUERY_LENGTH,
    MAX_TOP_K,
    RetrievalProfileResponse,
)


class GroundedAnswerRequest(BaseModel):
    """One grounded question.

    Deliberately the same four knobs a claim search takes, minus the two
    candidate counts. Those are a cost decision rather than a relevance one, and
    a caller that could inflate them could make one request sweep the whole
    index; the server picks them from configuration.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    #: Absent or empty means every indexed document. Duplicates are collapsed.
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_DOCUMENT_FILTER)
    mode: RetrievalMode = RetrievalMode.HYBRID
    top_k: int = Field(default=6, ge=1, le=MAX_TOP_K)

    @field_validator("query")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """A whitespace-only question passes min_length and retrieves nothing."""
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class GroundedSourceSpanResponse(BaseModel):
    """One canonical span, with the text stored at those coordinates.

    ``quote`` is read out of ``document_pages.text`` at ``locator``'s offsets by
    the server. It is never a model's reproduction of the text, which would be a
    second assertion about the source rather than a consequence of it.
    """

    locator: SourceLocator
    quote: str


class GroundedEvidenceResponse(BaseModel):
    """One piece of cited evidence, as the reader sees it.

    Carries the retrieval ranks so a reader can tell *why* this claim was in
    front of the model. Absence is preserved: a null ``dense_rank`` means the
    dense channel did not retrieve this claim, and must not be rendered as zero.
    """

    #: The identifier issued for this request. Meaningless in any other request,
    #: and returned only so statements can be matched to their evidence.
    evidence_id: str
    document_id: uuid.UUID
    document_name: str
    claim_number: int
    claim_type: ClaimType
    depends_on: list[int] = Field(default_factory=list)
    #: In span order. A claim crossing a page break keeps one span per page.
    source_spans: list[GroundedSourceSpanResponse]
    crosses_pages: bool

    fused_rank: int
    fused_score: float
    dense_rank: int | None = None
    dense_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None


class GroundedStatementResponse(BaseModel):
    """One statement and the evidence it was validated against."""

    text: str
    #: Never empty, deduplicated, and every entry present in ``evidence``.
    evidence_ids: list[str]


class GroundedRetrievalResponse(BaseModel):
    """What was searched, and how much of it reached the model."""

    mode: RetrievalMode
    profile: RetrievalProfileResponse
    #: Completed index runs the active profile matched. Zero means nothing is
    #: indexed for this profile - distinct from a question that matched nothing.
    searched_index_run_count: int
    retrieved_candidate_count: int
    included_evidence_count: int
    #: Retrieved claims dropped to stay inside the context budget. These were
    #: never shown to the model and could not have been cited.
    omitted_evidence_count: int


class GroundedAnswerResponse(BaseModel):
    """A grounded answer, or an honest account of why there is not one."""

    #: Composed by the server from the validated statements below, plus a fixed
    #: limitation sentence when evidence was insufficient. Plain text: render it
    #: as text, never as HTML or Markdown.
    answer: str
    statements: list[GroundedStatementResponse] = Field(default_factory=list)
    #: Only evidence actually cited by a validated statement. Retrieved claims
    #: the model did not use are not returned as though they supported anything.
    evidence: list[GroundedEvidenceResponse] = Field(default_factory=list)

    #: True is a normal 200 outcome, not an error. It means the retrieved claims
    #: do not answer the question - which is the correct answer to a great many
    #: questions, and the one a system like this must be willing to give.
    insufficient_evidence: bool
    insufficient_reason: InsufficientReason | None = None

    retrieval: GroundedRetrievalResponse
    #: ``None`` when no provider was contacted, which happens when retrieval
    #: returned nothing at all.
    generation: GenerationMetadataResponse | None = None
    warnings: list[str] = Field(default_factory=list)
