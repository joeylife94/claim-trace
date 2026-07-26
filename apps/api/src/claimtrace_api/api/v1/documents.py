"""Document ingestion endpoints."""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile
from sqlalchemy import func, select

from claimtrace_api.api.deps import IngestionServiceDep, SessionDep, SettingsDep
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import Document, DocumentPage
from claimtrace_api.schemas.documents import (
    DocumentListResponse,
    DocumentPageListResponse,
    DocumentPageResponse,
    DocumentResponse,
    IngestionErrorResponse,
)
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.services.ingestion import UploadPayload, read_upload

router = APIRouter(prefix="/documents", tags=["documents"])

#: Shared OpenAPI responses for the error envelope.
_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    HTTPStatus.BAD_REQUEST: {"model": IngestionErrorResponse},
    HTTPStatus.NOT_FOUND: {"model": IngestionErrorResponse},
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: {"model": IngestionErrorResponse},
    HTTPStatus.UNSUPPORTED_MEDIA_TYPE: {"model": IngestionErrorResponse},
    HTTPStatus.UNPROCESSABLE_ENTITY: {"model": IngestionErrorResponse},
}


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=HTTPStatus.CREATED,
    summary="Upload a PDF",
    description=(
        "Accepts one text-based PDF, stores the original, extracts text page by "
        "page, and returns the ingestion record.\n\n"
        "Uploading a file whose SHA-256 matches an existing document returns that "
        "document with 200 instead of creating a second copy."
    ),
    responses={HTTPStatus.OK: {"model": DocumentResponse}, **_ERROR_RESPONSES},
)
async def upload_document(
    response: Response,
    settings: SettingsDep,
    service: IngestionServiceDep,
    file: Annotated[UploadFile, File(description="A text-based PDF file.")],
) -> DocumentResponse:
    data = await read_upload(file.read, max_bytes=settings.upload_max_bytes)
    payload = UploadPayload(
        filename=file.filename or "",
        content_type=file.content_type or "",
        data=data,
    )

    result = await service.ingest(payload)
    if not result.created:
        # Idempotent re-upload: the caller already has this document.
        response.status_code = HTTPStatus.OK
    return DocumentResponse.model_validate(result.document)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    description="Document records ordered by creation time, newest first.",
)
async def list_documents(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    total = await session.scalar(select(func.count()).select_from(Document)) or 0
    result = await session.execute(
        select(Document)
        .order_by(Document.created_at.desc(), Document.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(row) for row in result.scalars()],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get a document",
    responses=_ERROR_RESPONSES,
)
async def get_document(document_id: uuid.UUID, session: SessionDep) -> DocumentResponse:
    document = await _require_document(document_id, session)
    return DocumentResponse.model_validate(document)


@router.get(
    "/{document_id}/pages",
    response_model=DocumentPageListResponse,
    summary="Get extracted page text",
    description=(
        "Pages in reading order. Each page carries the source locator that spans "
        "it, which is the coordinate future citations refine."
    ),
    responses=_ERROR_RESPONSES,
)
async def list_document_pages(
    document_id: uuid.UUID,
    session: SessionDep,
    page_number: Annotated[int | None, Query(ge=1, description="Return only this page.")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentPageListResponse:
    await _require_document(document_id, session)

    filters = [DocumentPage.document_id == document_id]
    if page_number is not None:
        filters.append(DocumentPage.page_number == page_number)

    total = (
        await session.scalar(select(func.count()).select_from(DocumentPage).where(*filters))
    ) or 0
    result = await session.execute(
        select(DocumentPage)
        .where(*filters)
        .order_by(DocumentPage.page_number.asc())
        .limit(limit)
        .offset(offset)
    )

    return DocumentPageListResponse(
        document_id=document_id,
        items=[_page_response(page) for page in result.scalars()],
        total=total,
        limit=limit,
        offset=offset,
    )


def _page_response(page: DocumentPage) -> DocumentPageResponse:
    return DocumentPageResponse(
        id=page.id,
        document_id=page.document_id,
        page_number=page.page_number,
        text=page.text,
        character_count=page.character_count,
        text_sha256=page.text_sha256,
        created_at=page.created_at,
        locator=SourceLocator(
            document_id=page.document_id,
            page_number=page.page_number,
            start_char=0,
            end_char=page.character_count,
        ),
    )


async def _require_document(document_id: uuid.UUID, session: SessionDep) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise AppError(ErrorCode.DOCUMENT_NOT_FOUND, "Document not found.")
    return document
