"""Request/response models for claim structural parsing.

Database identifiers stay server-side: claims are addressed by claim number,
which is what a reader and a citation both use. The one exception is the parse
result id, which the UI needs to tell two parser versions apart.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from claimtrace_api.db.models import ClaimParseStatus, ClaimType
from claimtrace_api.schemas.locators import SourceLocator


class ParseWarningResponse(BaseModel):
    """One structural problem the parser recorded without repairing."""

    code: str
    message: str
    claim_number: int | None = None


class ClaimSpanResponse(BaseModel):
    """One page-relative source span, with its resolvable locator."""

    sequence_number: int
    page_number: int
    start_char: int
    end_char: int
    #: The same coordinates as a SourceLocator, so the client can hand this
    #: straight to the page viewer without reassembling it.
    locator: SourceLocator


class ClaimResponse(BaseModel):
    """One parsed claim with its provenance and resolved references."""

    claim_number: int
    claim_type: ClaimType
    #: Reconstructed from the ordered spans, joined by the page separator.
    text: str
    #: Claim numbers this claim explicitly references, ascending. Empty for an
    #: independent claim, and empty when references could not be resolved - the
    #: reason is then in the parse result's warnings.
    depends_on: list[int] = Field(default_factory=list)
    spans: list[ClaimSpanResponse]
    #: True when the claim's source crosses a page break.
    crosses_pages: bool


class ClaimParseResultResponse(BaseModel):
    """Metadata for one parser version's run against one document."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    status: ClaimParseStatus
    parser_name: str
    parser_version: str
    claim_count: int
    warning_count: int
    warnings: list[ParseWarningResponse] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ClaimSetResponse(BaseModel):
    """A parse result together with its ordered claims."""

    result: ClaimParseResultResponse
    claims: list[ClaimResponse] = Field(default_factory=list)


class ClaimDetailResponse(BaseModel):
    """One claim, with enough parser metadata to interpret it on its own."""

    result: ClaimParseResultResponse
    claim: ClaimResponse
