"""Regression coverage for post-registration storage read failures."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.db.models import DocumentStatus
from claimtrace_api.parsing.pymupdf_parser import PyMuPDFDocumentParser
from claimtrace_api.services.ingestion import (
    DocumentIngestionError,
    DocumentIngestionService,
    UploadPayload,
)
from claimtrace_api.storage.base import StorageError
from claimtrace_api.storage.local import LocalFileStorage
from tests.conftest import StubSession, capture_logs
from tests.pdf_factory import build_text_pdf


class ReadFailingStorage(LocalFileStorage):
    """Allow the initial write, then fail the parse-time read deterministically."""

    def read(self, key: str) -> bytes:
        raise StorageError("synthetic read failure")


async def test_storage_read_failure_marks_document_failed_and_logs_safe_event(
    settings: Settings,
    stub_session: StubSession,
    storage_root: Path,
) -> None:
    service = DocumentIngestionService(
        session=cast(AsyncSession, stub_session),
        storage=ReadFailingStorage(storage_root),
        parser=PyMuPDFDocumentParser(),
        settings=settings,
    )
    payload = UploadPayload(
        filename="patent.pdf",
        content_type="application/pdf",
        data=build_text_pdf(),
    )

    with (
        capture_logs("claimtrace_api.services.ingestion", logging.INFO) as records,
        pytest.raises(DocumentIngestionError) as excinfo,
    ):
        await service.ingest(payload)

    error = excinfo.value
    assert error.code is ErrorCode.STORAGE_FAILURE
    assert error.document.status is DocumentStatus.FAILED
    assert error.document.error_code == ErrorCode.STORAGE_FAILURE.value
    assert "synthetic read failure" not in error.message

    events = [record for record in records if record.getMessage() == "document ingestion finished"]
    assert len(events) == 1
    event = events[0]
    assert event.status == "failed"
    assert event.error_code == ErrorCode.STORAGE_FAILURE.value
    rendered = " ".join(f"{record.getMessage()} {record.__dict__}" for record in records)
    assert "synthetic read failure" not in rendered
