"""Request/response models for document ingestion.

``storage_key`` is intentionally absent from every response: where bytes live on
disk is server-side detail, and exposing it invites path probing.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from claimtrace_api.db.models import DocumentStatus
from claimtrace_api.schemas.locators import SourceLocator


class DocumentResponse(BaseModel):
    """Full ingestion record for one document."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    page_count: int | None = None
    extracted_character_count: int | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """One page of document records, newest first."""

    items: list[DocumentResponse]
    total: int = Field(description="Total documents available, ignoring limit/offset.")
    limit: int
    offset: int


class DocumentPageResponse(BaseModel):
    """A single page of extracted text with its canonical locator."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    text: str
    character_count: int
    text_sha256: str
    created_at: datetime
    #: The span covering this whole page. Narrower citations are sub-spans of it.
    locator: SourceLocator


class DocumentPageListResponse(BaseModel):
    """Ordered pages for one document."""

    document_id: uuid.UUID
    items: list[DocumentPageResponse]
    total: int
    limit: int
    offset: int


class IngestionErrorResponse(BaseModel):
    """Error envelope for a rejected or unparseable upload.

    ``document`` is present when the failure happened after the file was stored,
    so the client can link to a traceable record instead of just showing a message.
    """

    detail: str
    error_code: str
    document: DocumentResponse | None = None
