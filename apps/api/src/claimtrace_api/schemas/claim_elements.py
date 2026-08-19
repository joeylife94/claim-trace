"""Public response contract for deterministic claim-element decomposition."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from claimtrace_api.schemas.locators import SourceLocator


class ElementWarningResponse(BaseModel):
    """A persisted deterministic-parser warning, never a legal conclusion."""

    code: str
    message: str


class ClaimElementSpanResponse(BaseModel):
    sequence_number: int = Field(ge=0)
    page_number: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    locator: SourceLocator


class ClaimElementResponse(BaseModel):
    id: uuid.UUID
    sequence_number: int = Field(ge=0)
    text: str = Field(min_length=1)
    spans: list[ClaimElementSpanResponse]


class ElementDecompositionResponse(BaseModel):
    """One persisted machine decomposition run and its source-backed elements."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    claim_id: uuid.UUID
    parser_name: str
    parser_version: str
    element_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    warnings: list[ElementWarningResponse]
    elements: list[ClaimElementResponse]
    created_at: datetime
