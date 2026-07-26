"""PyMuPDF-backed parser for digital (text-layer) PDFs.

Scope: PDFs that already carry a text layer. A scanned page contains an image and
no text, and this parser reports that honestly rather than guessing - OCR is a
later phase with different accuracy and provenance characteristics.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

import pymupdf

from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.parsing.base import ParsedDocument, ParsedPage, ParserError

logger = logging.getLogger(__name__)

#: Document-level PDF metadata worth keeping. Everything else is dropped rather
#: than stored blindly, since PDF metadata is attacker-controlled input.
_METADATA_KEYS = ("title", "author", "subject", "keywords", "creator", "producer")

#: Longest metadata value kept, to bound what an uploaded file can push into logs
#: and responses.
_METADATA_VALUE_LIMIT = 512


def _pymupdf_version() -> str:
    try:
        return package_version("pymupdf")
    except PackageNotFoundError:  # pragma: no cover - only when installed oddly
        return str(getattr(pymupdf, "__version__", "unknown"))


def normalise_page_text(raw: str) -> str:
    """Canonicalise extracted text before it is persisted.

    Only line endings are touched. The result is the exact string stored in
    ``document_pages.text``, and therefore the string every source locator's
    character offsets refer to - so this transformation must stay deterministic.
    """
    return raw.replace("\r\n", "\n").replace("\r", "\n")


class PyMuPDFDocumentParser:
    """Extracts ordered page text from a digital PDF."""

    def __init__(self) -> None:
        self._version = _pymupdf_version()

    @property
    def name(self) -> str:
        return "pymupdf-digital-text"

    @property
    def version(self) -> str:
        return self._version

    def supports(self, *, content_type: str, filename: str) -> bool:
        return content_type.lower() == "application/pdf" or filename.lower().endswith(".pdf")

    def parse(self, data: bytes) -> ParsedDocument:
        """Extract every page's text in document order."""
        try:
            document = pymupdf.open(stream=data, filetype="pdf")
        except Exception as exc:
            # The cause is logged, never returned: it can quote file contents.
            logger.info("pdf could not be opened", extra={"reason": type(exc).__name__})
            raise ParserError(
                ErrorCode.MALFORMED_PDF,
                "The file could not be read as a PDF. It may be corrupted or truncated.",
            ) from exc

        with document:
            if document.needs_pass or document.is_encrypted:
                raise ParserError(
                    ErrorCode.ENCRYPTED_PDF,
                    "The PDF is password protected. Remove the protection and upload it again.",
                )

            if document.page_count == 0:
                # PyMuPDF silently repairs some damaged files into an empty
                # document. That is a broken PDF, not a scanned one, so it gets
                # the structural error code rather than the no-text one.
                raise ParserError(
                    ErrorCode.MALFORMED_PDF,
                    "The PDF contains no pages. It may be corrupted or truncated.",
                )

            try:
                pages = [
                    ParsedPage(
                        page_number=index + 1,
                        text=normalise_page_text(page.get_text("text")),
                    )
                    for index, page in enumerate(document)
                ]
            except Exception as exc:
                logger.info("pdf page extraction failed", extra={"reason": type(exc).__name__})
                raise ParserError(
                    ErrorCode.MALFORMED_PDF,
                    "The PDF could not be read to the end. It may be corrupted.",
                ) from exc

            metadata = self._safe_metadata(document.metadata)

        return ParsedDocument(
            pages=tuple(pages),
            parser_name=self.name,
            parser_version=self.version,
            metadata=metadata,
        )

    @staticmethod
    def _safe_metadata(raw: dict[str, str | None] | None) -> dict[str, str]:
        """Keep a known subset of PDF metadata, truncated and stringified."""
        if not raw:
            return {}
        return {
            key: str(raw[key])[:_METADATA_VALUE_LIMIT] for key in _METADATA_KEYS if raw.get(key)
        }
