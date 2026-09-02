"""Explicit recovery of a terminal failed document from its persisted original."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import Document, DocumentPage, DocumentStatus
from claimtrace_api.parsing.pymupdf_parser import PyMuPDFDocumentParser
from claimtrace_api.services.ingestion import DocumentIngestionService
from claimtrace_api.storage.local import LocalFileStorage, build_storage_key
from tests.conftest import StubSession
from tests.pdf_factory import build_text_pdf


class RetrySession(StubSession):
    """Stub session that exposes one already-persisted document."""

    def __init__(self, document: Document) -> None:
        super().__init__()
        self.document = document
        self.get_kwargs: dict[str, Any] = {}

    async def get(self, *_args: Any, **kwargs: Any) -> Document:
        self.get_kwargs = kwargs
        return self.document


def failed_document(pdf: bytes) -> Document:
    digest = hashlib.sha256(pdf).hexdigest()
    return Document(
        id=uuid.uuid4(),
        original_filename="retry-source.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf),
        sha256=digest,
        storage_key=build_storage_key(digest),
        status=DocumentStatus.FAILED,
        error_code=ErrorCode.STORAGE_FAILURE.value,
        error_message="temporary storage outage",
    )


def make_service(
    settings: Settings,
    session: StubSession,
    storage_root: Path,
) -> DocumentIngestionService:
    return DocumentIngestionService(
        session=cast(AsyncSession, session),
        storage=LocalFileStorage(storage_root),
        parser=PyMuPDFDocumentParser(),
        settings=settings,
    )


async def test_retry_reuses_failed_document_and_persisted_original(
    settings: Settings,
    storage_root: Path,
) -> None:
    pdf = build_text_pdf()
    document = failed_document(pdf)
    storage = LocalFileStorage(storage_root)
    storage.write(document.storage_key, pdf)
    session = RetrySession(document)
    service = make_service(settings, session, storage_root)

    result = await service.retry(document.id)

    assert result.created is False
    assert result.document is document
    assert result.document.status is DocumentStatus.COMPLETED
    assert result.document.error_code is None
    assert result.document.error_message is None
    assert result.document.page_count == 2
    assert result.document.sha256 == hashlib.sha256(pdf).hexdigest()
    assert result.document.storage_key == build_storage_key(result.document.sha256)
    assert session.get_kwargs == {"with_for_update": True}
    assert storage.read(document.storage_key) == pdf
    pages = [item for item in session.added if isinstance(item, DocumentPage)]
    assert len(pages) == 2
    assert all(page.document_id == document.id for page in pages)


async def test_retry_rejects_non_failed_document(
    settings: Settings,
    storage_root: Path,
) -> None:
    pdf = build_text_pdf()
    document = failed_document(pdf)
    document.status = DocumentStatus.COMPLETED
    session = RetrySession(document)
    service = make_service(settings, session, storage_root)

    with pytest.raises(AppError) as excinfo:
        await service.retry(document.id)

    assert excinfo.value.code is ErrorCode.DOCUMENT_RETRY_NOT_ALLOWED
    assert document.status is DocumentStatus.COMPLETED
    assert session.commits == 0


@pytest.mark.integration
async def test_retry_api_recovers_same_row_and_source_pages_on_postgres(
    integration_client: TestClient,
    integration_settings: Settings,
    sync_engine: Any,
) -> None:
    pdf = build_text_pdf(("retry page one source evidence", "retry page two source evidence"))
    document = failed_document(pdf)
    storage = LocalFileStorage(integration_settings.storage_root)
    storage.write(document.storage_key, pdf)

    with Session(sync_engine) as session:
        session.add(document)
        session.commit()
        document_id = document.id
        original_sha = document.sha256
        original_storage_key = document.storage_key

    response = integration_client.post(f"/api/v1/documents/{document_id}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(document_id)
    assert body["status"] == "completed"
    assert body["error_code"] is None
    assert body["error_message"] is None
    assert body["page_count"] == 2

    with Session(sync_engine) as session:
        persisted = session.get(Document, document_id)
        assert persisted is not None
        assert persisted.sha256 == original_sha
        assert persisted.storage_key == original_storage_key
        assert persisted.status is DocumentStatus.COMPLETED
        assert persisted.error_code is None
        assert persisted.error_message is None
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        pages = list(
            session.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            )
        )
        assert len(pages) == 2
        assert [page.text_sha256 for page in pages] == [
            hashlib.sha256(page.text.encode("utf-8")).hexdigest() for page in pages
        ]


@pytest.mark.integration
async def test_retry_api_rejects_completed_document_with_stable_conflict(
    integration_client: TestClient,
    integration_settings: Settings,
    sync_engine: Any,
) -> None:
    pdf = build_text_pdf()
    document = failed_document(pdf)
    document.status = DocumentStatus.COMPLETED
    document.error_code = None
    document.error_message = None
    LocalFileStorage(integration_settings.storage_root).write(document.storage_key, pdf)

    with Session(sync_engine) as session:
        session.add(document)
        session.commit()
        document_id = document.id

    response = integration_client.post(f"/api/v1/documents/{document_id}/retry")

    assert response.status_code == 409
    assert response.json()["error_code"] == ErrorCode.DOCUMENT_RETRY_NOT_ALLOWED.value
