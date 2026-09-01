"""Regression coverage for page-persistence transaction failures."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.db.models import Document, DocumentPage, DocumentStatus
from claimtrace_api.parsing.pymupdf_parser import PyMuPDFDocumentParser
from claimtrace_api.services.ingestion import (
    DocumentIngestionError,
    DocumentIngestionService,
    UploadPayload,
)
from claimtrace_api.storage.local import LocalFileStorage
from tests.conftest import StubSession, capture_logs
from tests.pdf_factory import build_text_pdf


class PageCommitFailingSession(StubSession):
    """Fail exactly the page/completed transaction and model rollback of its pages."""

    def __init__(self) -> None:
        super().__init__()
        self.rollbacks = 0
        self.persisted_pages: list[DocumentPage] = []

    async def commit(self) -> None:
        next_commit = self.commits + 1
        if next_commit == 3:
            self.commits = next_commit
            raise RuntimeError("synthetic database detail: page commit failed")
        await super().commit()
        self.persisted_pages = [obj for obj in self.added if isinstance(obj, DocumentPage)]

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.added = [obj for obj in self.added if not isinstance(obj, DocumentPage)]


async def test_page_persistence_failure_terminalizes_document_and_logs_safe_event(
    settings: Settings,
    storage_root: Path,
) -> None:
    session = PageCommitFailingSession()
    service = DocumentIngestionService(
        session=cast(AsyncSession, session),
        storage=LocalFileStorage(storage_root),
        parser=PyMuPDFDocumentParser(),
        settings=settings,
    )
    upload = UploadPayload(
        filename="patent.pdf",
        content_type="application/pdf",
        data=build_text_pdf(),
    )

    with (
        capture_logs("claimtrace_api.services.ingestion", logging.INFO) as records,
        pytest.raises(DocumentIngestionError) as excinfo,
    ):
        await service.ingest(upload)

    error = excinfo.value
    assert error.code is ErrorCode.INTERNAL_ERROR
    assert error.document.status is DocumentStatus.FAILED
    assert error.document.error_code == ErrorCode.INTERNAL_ERROR.value
    assert error.document.page_count is None
    assert error.document.extracted_character_count is None
    assert session.persisted_pages == []
    assert session.rollbacks >= 2
    assert "synthetic database detail" not in error.message

    documents = [obj for obj in session.added if isinstance(obj, Document)]
    assert len(documents) == 1
    assert documents[0].status is DocumentStatus.FAILED

    events = [record for record in records if record.getMessage() == "document ingestion finished"]
    assert len(events) == 1
    event = events[0]
    assert event.status == "failed"
    assert event.error_code == ErrorCode.INTERNAL_ERROR.value
    rendered = " ".join(f"{record.getMessage()} {record.__dict__}" for record in records)
    assert "synthetic database detail" not in rendered
