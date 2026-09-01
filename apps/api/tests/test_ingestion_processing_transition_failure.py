"""Regression coverage for processing-transition commit failures."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.db.models import Document, DocumentStatus
from claimtrace_api.parsing.pymupdf_parser import PyMuPDFDocumentParser
from claimtrace_api.services.ingestion import (
    DocumentIngestionError,
    DocumentIngestionService,
    UploadPayload,
)
from claimtrace_api.storage.local import LocalFileStorage
from tests.conftest import StubSession, capture_logs
from tests.pdf_factory import build_text_pdf


class ProcessingCommitFailingSession(StubSession):
    """Fail exactly the uploaded-to-processing commit and model its rollback."""

    def __init__(self) -> None:
        super().__init__()
        self.rollbacks = 0
        self.persisted_status = DocumentStatus.UPLOADED

    async def commit(self) -> None:
        next_commit = self.commits + 1
        if next_commit == 2:
            self.commits = next_commit
            raise RuntimeError("synthetic database detail: processing transition failed")
        await super().commit()
        documents = [obj for obj in self.added if isinstance(obj, Document)]
        if documents:
            self.persisted_status = documents[0].status

    async def rollback(self) -> None:
        self.rollbacks += 1
        documents = [obj for obj in self.added if isinstance(obj, Document)]
        if documents and self.commits == 2:
            documents[0].status = self.persisted_status


async def test_processing_transition_failure_terminalizes_document_and_logs_safe_event(
    settings: Settings,
    storage_root: Path,
) -> None:
    session = ProcessingCommitFailingSession()
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
    assert session.persisted_status is DocumentStatus.FAILED
    assert session.commits == 3
    assert session.rollbacks >= 1
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
