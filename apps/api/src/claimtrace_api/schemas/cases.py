"""Schemas for the bounded D5 persistent analyst Case workspace."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CaseCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("title must contain non-whitespace characters")
        return title


class CaseDocumentResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    status: str
    associated_at: datetime


class CaseResponse(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    documents: list[CaseDocumentResponse] = Field(default_factory=list)


class CaseListResponse(BaseModel):
    items: list[CaseResponse] = Field(default_factory=list)


class CaseDocumentMutationResponse(BaseModel):
    case: CaseResponse
    changed: bool
