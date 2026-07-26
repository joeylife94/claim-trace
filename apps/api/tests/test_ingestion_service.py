"""Ingestion service behaviour that is independent of HTTP and of a database."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import ErrorCode, IngestionError
from claimtrace_api.db.models import Document, DocumentStatus
from claimtrace_api.parsing.pymupdf_parser import PyMuPDFDocumentParser
from claimtrace_api.services.ingestion import (
    DocumentIngestionError,
    DocumentIngestionService,
    UploadPayload,
    read_upload,
)
from claimtrace_api.storage.local import LocalFileStorage, build_storage_key
from tests.conftest import StubResult, StubSession, capture_logs
from tests.pdf_factory import build_text_pdf


def make_service(
    settings: Settings, session: StubSession, storage_root: Path
) -> DocumentIngestionService:
    return DocumentIngestionService(
        session=cast(AsyncSession, session),
        storage=LocalFileStorage(storage_root),
        parser=PyMuPDFDocumentParser(),
        settings=settings,
    )


def payload(data: bytes, *, filename: str = "patent.pdf") -> UploadPayload:
    return UploadPayload(filename=filename, content_type="application/pdf", data=data)


# -- streaming size guard ---------------------------------------------------


async def test_read_upload_returns_the_whole_stream() -> None:
    chunks = [b"abc", b"def", b""]

    async def read(_size: int) -> bytes:
        return chunks.pop(0)

    assert await read_upload(read, max_bytes=100) == b"abcdef"


async def test_read_upload_stops_before_buffering_an_oversized_body() -> None:
    """The guard must trip while streaming, not after the whole body is in memory."""
    reads = 0

    async def read(size: int) -> bytes:
        nonlocal reads
        reads += 1
        return b"x" * size

    with pytest.raises(IngestionError) as excinfo:
        await read_upload(read, max_bytes=10, chunk_size=4)

    assert excinfo.value.code is ErrorCode.FILE_TOO_LARGE
    assert reads == 3  # 4 + 4 + 4 > 10, and it stopped there


# -- ingestion --------------------------------------------------------------


async def test_successful_ingest_records_parser_identity(
    settings: Settings, stub_session: StubSession, storage_root: Path
) -> None:
    service = make_service(settings, stub_session, storage_root)
    pdf = build_text_pdf()

    result = await service.ingest(payload(pdf))

    assert result.created is True
    assert result.document.status is DocumentStatus.COMPLETED
    assert result.document.sha256 == hashlib.sha256(pdf).hexdigest()
    assert result.document.parser_name == "pymupdf-digital-text"
    assert result.document.page_count == 2


async def test_storage_key_is_derived_from_content_not_filename(
    settings: Settings, stub_session: StubSession, storage_root: Path
) -> None:
    service = make_service(settings, stub_session, storage_root)
    pdf = build_text_pdf()

    result = await service.ingest(payload(pdf, filename="../../etc/passwd.pdf"))

    assert result.document.storage_key == build_storage_key(hashlib.sha256(pdf).hexdigest())
    assert ".." not in result.document.storage_key
    # The hostile name is retained for display only, never used as a path.
    assert result.document.original_filename == "../../etc/passwd.pdf"
    assert not (storage_root.parent.parent / "etc").exists()


async def test_duplicate_returns_the_existing_document_without_rewriting(
    settings: Settings, storage_root: Path
) -> None:
    pdf = build_text_pdf()
    existing = Document(
        original_filename="already-here.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf),
        sha256=hashlib.sha256(pdf).hexdigest(),
        storage_key="ab/existing.pdf",
        status=DocumentStatus.COMPLETED,
    )

    class DuplicateSession(StubSession):
        async def execute(self, *_args: Any, **_kwargs: Any) -> StubResult:
            return StubResult(existing)

    session = DuplicateSession()
    service = make_service(settings, session, storage_root)

    result = await service.ingest(payload(pdf))

    assert result.created is False
    assert result.document is existing
    assert session.added == []
    # Nothing new was written to storage.
    assert list(storage_root.rglob("*.pdf")) == []


async def test_page_persistence_failure_rolls_back_and_propagates(
    settings: Settings, storage_root: Path
) -> None:
    """A failed page write must never leave a document looking completed."""

    class FailingSession(StubSession):
        def __init__(self) -> None:
            super().__init__()
            self.rollbacks = 0

        async def commit(self) -> None:
            await super().commit()
            # First two commits register the document; the third writes pages.
            if self.commits >= 3:
                raise RuntimeError("connection lost")

        async def rollback(self) -> None:
            self.rollbacks += 1

    session = FailingSession()
    service = make_service(settings, session, storage_root)

    with pytest.raises(RuntimeError, match="connection lost"):
        await service.ingest(payload(build_text_pdf()))

    assert session.rollbacks == 1
    documents = [obj for obj in session.added if isinstance(obj, Document)]
    assert documents[0].status is not DocumentStatus.COMPLETED


async def test_parse_failure_marks_the_document_failed(
    settings: Settings, stub_session: StubSession, storage_root: Path
) -> None:
    service = make_service(settings, stub_session, storage_root)

    with pytest.raises(DocumentIngestionError) as excinfo:
        await service.ingest(payload(b"%PDF-1.7 truncated"))

    assert excinfo.value.code is ErrorCode.MALFORMED_PDF
    assert excinfo.value.document.status is DocumentStatus.FAILED
    assert excinfo.value.document.error_code == ErrorCode.MALFORMED_PDF.value


async def test_no_extractable_text_threshold_comes_from_settings(
    settings: Settings, stub_session: StubSession, storage_root: Path
) -> None:
    """Raising the threshold rejects a document that would otherwise pass."""
    strict = settings.model_copy(update={"min_extracted_characters": 10_000})
    service = make_service(strict, stub_session, storage_root)

    with pytest.raises(DocumentIngestionError) as excinfo:
        await service.ingest(payload(build_text_pdf()))

    assert excinfo.value.code is ErrorCode.NO_EXTRACTABLE_TEXT


async def test_stored_bytes_match_the_upload(
    settings: Settings, stub_session: StubSession, storage_root: Path
) -> None:
    service = make_service(settings, stub_session, storage_root)
    pdf = build_text_pdf()

    result = await service.ingest(payload(pdf))

    stored = LocalFileStorage(storage_root).read(result.document.storage_key)
    assert stored == pdf


# -- observability ----------------------------------------------------------


INGESTION_LOGGER = "claimtrace_api.services.ingestion"


def finished_event(records: list[logging.LogRecord]) -> logging.LogRecord:
    matches = [r for r in records if r.getMessage() == "document ingestion finished"]
    assert len(matches) == 1, "expected exactly one completion event per ingestion"
    return matches[0]


async def test_ingestion_event_carries_the_documented_fields(
    settings: Settings, stub_session: StubSession, storage_root: Path
) -> None:
    service = make_service(settings, stub_session, storage_root)

    with capture_logs(INGESTION_LOGGER, logging.INFO) as records:
        result = await service.ingest(payload(build_text_pdf()))

    record = finished_event(records)
    assert record.document_id == str(result.document.id)
    assert record.size_bytes == result.document.size_bytes
    assert record.parser_name == "pymupdf-digital-text"
    assert record.parser_version
    assert record.page_count == 2
    assert record.status == "completed"
    assert record.error_code is None
    assert isinstance(record.duration_ms, float)


async def test_ingestion_event_logs_a_digest_prefix_not_the_whole_hash(
    settings: Settings, stub_session: StubSession, storage_root: Path
) -> None:
    """A full digest in a log is enough to prove possession of a document."""
    pdf = build_text_pdf()
    service = make_service(settings, stub_session, storage_root)

    with capture_logs(INGESTION_LOGGER, logging.INFO) as records:
        await service.ingest(payload(pdf))

    full_digest = hashlib.sha256(pdf).hexdigest()
    assert finished_event(records).sha256_prefix == full_digest[:12]
    assert all(full_digest not in r.getMessage() for r in records)


async def test_failed_ingestion_event_reports_the_error_code(
    settings: Settings, stub_session: StubSession, storage_root: Path
) -> None:
    service = make_service(settings, stub_session, storage_root)

    with (
        capture_logs(INGESTION_LOGGER, logging.INFO) as records,
        pytest.raises(DocumentIngestionError),
    ):
        await service.ingest(payload(b"%PDF-1.7\n" + bytes(range(256))))

    record = finished_event(records)
    assert record.status == "failed"
    assert record.error_code == ErrorCode.MALFORMED_PDF.value


async def test_logs_never_contain_extracted_text(
    settings: Settings, stub_session: StubSession, storage_root: Path
) -> None:
    marker = "CONFIDENTIAL PATENT BODY TEXT THAT MUST NOT BE LOGGED"
    service = make_service(settings, stub_session, storage_root)

    with capture_logs("claimtrace_api", logging.DEBUG) as records:
        await service.ingest(payload(build_text_pdf((marker,))))

    assert records, "the capture must not be vacuously empty"
    rendered = " ".join(f"{r.getMessage()} {r.__dict__}" for r in records)
    assert "CONFIDENTIAL" not in rendered
