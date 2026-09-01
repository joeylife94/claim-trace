"""Document ingestion use case.

Order of operations, and why:

1. Validate cheaply (extension, declared type, size, magic bytes) before anything
   is written. A rejected upload leaves no trace, because it never became a
   document.
2. Hash the bytes and look for an existing document with the same digest.
   Duplicates return the existing record; the same bytes are never stored twice.
3. Store the original, then commit a ``uploaded`` row. From here on a failure is
   traceable: the record survives and carries an error code.
4. Parse, then write every page and the ``completed`` status in a single
   transaction, so a partial page set can never be presented as a finished
   document.

Parsing is synchronous. For a 20 MB text PDF this is a sub-second operation, and
a queue would add operational surface without buying anything at this stage.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import Document, DocumentPage, DocumentStatus
from claimtrace_api.parsing.base import DocumentParser, ParsedDocument, ParserError
from claimtrace_api.storage.base import FileStorage, StorageError
from claimtrace_api.storage.local import build_storage_key

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
SHA_LOG_PREFIX = 12


class DocumentIngestionError(AppError):
    """An ingestion failure that left a traceable document record behind."""

    def __init__(self, code: ErrorCode, message: str, document: Document) -> None:
        super().__init__(code, message)
        self.document = document


@dataclass(frozen=True, slots=True)
class UploadPayload:
    """One uploaded file, already read into memory and bounded by the size limit."""

    filename: str
    content_type: str
    data: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.data)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Outcome of an ingest call."""

    document: Document
    created: bool


async def read_upload(
    read: Callable[[int], Awaitable[bytes]],
    *,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> bytes:
    """Read an upload stream, refusing to buffer more than ``max_bytes``."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise AppError(
                ErrorCode.FILE_TOO_LARGE,
                f"The file exceeds the maximum upload size of {max_bytes} bytes.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


class DocumentIngestionService:
    """Coordinates validation, storage, parsing, and persistence."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        storage: FileStorage,
        parser: DocumentParser,
        settings: Settings,
    ) -> None:
        self._session = session
        self._storage = storage
        self._parser = parser
        self._settings = settings

    async def ingest(self, payload: UploadPayload) -> IngestionResult:
        """Ingest one uploaded file."""
        started = time.perf_counter()
        self._validate(payload)

        sha256 = hashlib.sha256(payload.data).hexdigest()
        existing = await self._find_by_sha256(sha256)
        if existing is not None:
            return self._duplicate(existing, sha256)

        try:
            document = await self._store_and_register(payload, sha256)
        except _DuplicateRace as race:
            return self._duplicate(race.document, sha256)

        try:
            parsed = self._parse(document)
            await self._persist_pages(document, parsed)
        except _ParseRejected as rejected:
            failed = await self._mark_failed(document, rejected.code, rejected.message)
            self._log_outcome(failed, started, error_code=rejected.code)
            raise DocumentIngestionError(rejected.code, rejected.message, failed) from rejected

        self._log_outcome(document, started)
        return IngestionResult(document=document, created=True)

    def _duplicate(self, existing: Document, sha256: str) -> IngestionResult:
        logger.info(
            "document ingestion skipped: duplicate",
            extra={
                "document_id": str(existing.id),
                "sha256_prefix": sha256[:SHA_LOG_PREFIX],
                "status": existing.status.value,
            },
        )
        return IngestionResult(document=existing, created=False)

    def _validate(self, payload: UploadPayload) -> None:
        filename = payload.filename.strip()
        if not filename:
            raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE, "A filename is required.")

        allowed_extensions = self._settings.upload_allowed_extensions
        if not any(filename.lower().endswith(ext) for ext in allowed_extensions):
            raise AppError(
                ErrorCode.UNSUPPORTED_FILE_TYPE,
                f"Only {', '.join(allowed_extensions)} files are accepted.",
            )

        declared_type = payload.content_type.split(";")[0].strip().lower()
        if declared_type not in self._settings.upload_allowed_content_types:
            raise AppError(
                ErrorCode.UNSUPPORTED_FILE_TYPE,
                f"Unsupported content type '{declared_type}'. Upload a PDF file.",
            )

        if payload.size_bytes == 0:
            raise AppError(ErrorCode.EMPTY_FILE, "The uploaded file is empty.")

        if payload.size_bytes > self._settings.upload_max_bytes:
            raise AppError(
                ErrorCode.FILE_TOO_LARGE,
                f"The file exceeds the maximum upload size of "
                f"{self._settings.upload_max_bytes} bytes.",
            )

        if not payload.data.startswith(PDF_MAGIC):
            raise AppError(
                ErrorCode.UNSUPPORTED_FILE_TYPE,
                "The file is not a PDF. Its contents do not begin with a PDF signature.",
            )

        if not self._parser.supports(content_type=declared_type, filename=filename):
            raise AppError(
                ErrorCode.UNSUPPORTED_FILE_TYPE,
                "No parser is available for this file type.",
            )

    async def _find_by_sha256(self, sha256: str) -> Document | None:
        result = await self._session.execute(select(Document).where(Document.sha256 == sha256))
        return result.scalar_one_or_none()

    async def _store_and_register(self, payload: UploadPayload, sha256: str) -> Document:
        storage_key = build_storage_key(sha256)
        try:
            self._storage.write(storage_key, payload.data)
        except StorageError as exc:
            logger.error("upload storage failed", extra={"sha256_prefix": sha256[:SHA_LOG_PREFIX]})
            raise AppError(
                ErrorCode.STORAGE_FAILURE,
                "The file could not be stored. Try again.",
            ) from exc

        document = Document(
            id=uuid.uuid4(),
            original_filename=payload.filename.strip()[:512],
            content_type=payload.content_type.split(";")[0].strip().lower()[:128],
            size_bytes=payload.size_bytes,
            sha256=sha256,
            storage_key=storage_key,
            status=DocumentStatus.UPLOADED,
        )
        self._session.add(document)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self._find_by_sha256(sha256)
            if existing is None:
                raise
            raise _DuplicateRace(existing) from None
        except BaseException:
            await self._session.rollback()
            self._storage.delete(storage_key)
            raise

        await self._session.refresh(document)
        document.status = DocumentStatus.PROCESSING
        await self._session.commit()
        await self._session.refresh(document)
        return document

    def _parse(self, document: Document) -> ParsedDocument:
        try:
            data = self._storage.read(document.storage_key)
        except StorageError as exc:
            raise _ParseRejected(
                ErrorCode.STORAGE_FAILURE,
                "The stored file could not be read. Try the upload again.",
            ) from exc

        try:
            return self._parser.parse(data)
        except ParserError as exc:
            raise _ParseRejected(exc.code, exc.message) from exc

    async def _persist_pages(self, document: Document, parsed: ParsedDocument) -> None:
        if parsed.character_count < self._settings.min_extracted_characters:
            raise _ParseRejected(
                ErrorCode.NO_EXTRACTABLE_TEXT,
                "No extractable text was found. Scanned or image-only PDFs are not "
                "supported yet; upload a PDF that contains a text layer.",
            )

        self._session.add_all(
            [
                DocumentPage(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    page_number=page.page_number,
                    text=page.text,
                    character_count=page.character_count,
                    text_sha256=hashlib.sha256(page.text.encode("utf-8")).hexdigest(),
                )
                for page in parsed.pages
            ]
        )
        document.page_count = parsed.page_count
        document.extracted_character_count = parsed.character_count
        document.parser_name = parsed.parser_name
        document.parser_version = parsed.parser_version
        document.status = DocumentStatus.COMPLETED
        document.error_code = None
        document.error_message = None

        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            document.status = DocumentStatus.PROCESSING
            document.page_count = None
            document.extracted_character_count = None
            logger.error(
                "document page persistence failed",
                extra={"document_id": str(document.id), "page_count": parsed.page_count},
            )
            raise
        await self._session.refresh(document)

    async def _mark_failed(self, document: Document, code: ErrorCode, message: str) -> Document:
        await self._session.rollback()
        document.status = DocumentStatus.FAILED
        document.error_code = code.value
        document.error_message = message[:512]
        document.page_count = None
        document.extracted_character_count = None
        await self._session.commit()
        await self._session.refresh(document)
        return document

    def _log_outcome(
        self,
        document: Document,
        started: float,
        *,
        error_code: ErrorCode | None = None,
    ) -> None:
        logger.info(
            "document ingestion finished",
            extra={
                "document_id": str(document.id),
                "size_bytes": document.size_bytes,
                "sha256_prefix": document.sha256[:SHA_LOG_PREFIX],
                "parser_name": document.parser_name,
                "parser_version": document.parser_version,
                "page_count": document.page_count,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "status": document.status.value,
                "error_code": error_code.value if error_code else None,
            },
        )


class _ParseRejected(Exception):
    """Internal signal: the stored document cannot be parsed."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _DuplicateRace(Exception):
    """Internal signal: a concurrent request stored this digest first."""

    def __init__(self, document: Document) -> None:
        super().__init__("duplicate document")
        self.document = document
