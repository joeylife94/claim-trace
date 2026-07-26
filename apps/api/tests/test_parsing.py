"""PyMuPDF parser behaviour."""

from __future__ import annotations

import pytest

from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.parsing.base import ParsedPage, ParserError
from claimtrace_api.parsing.pymupdf_parser import PyMuPDFDocumentParser, normalise_page_text
from tests.pdf_factory import (
    build_encrypted_pdf,
    build_malformed_pdf,
    build_non_pdf_bytes,
    build_pdf_without_text,
    build_text_pdf,
    build_truncated_pdf,
)


@pytest.fixture
def parser() -> PyMuPDFDocumentParser:
    return PyMuPDFDocumentParser()


def test_parses_pages_in_order(parser: PyMuPDFDocumentParser) -> None:
    parsed = parser.parse(build_text_pdf(("First page text.", "Second page text.")))

    assert parsed.page_count == 2
    assert [page.page_number for page in parsed.pages] == [1, 2]
    assert "First page text." in parsed.pages[0].text
    assert "Second page text." in parsed.pages[1].text


def test_reports_parser_identity(parser: PyMuPDFDocumentParser) -> None:
    parsed = parser.parse(build_text_pdf())

    assert parsed.parser_name == "pymupdf-digital-text"
    assert parsed.parser_version
    assert parsed.character_count == sum(len(page.text) for page in parsed.pages)


def test_keeps_known_metadata_only(parser: PyMuPDFDocumentParser) -> None:
    parsed = parser.parse(build_text_pdf(title="Synthetic Patent"))

    assert parsed.metadata.get("title") == "Synthetic Patent"
    assert set(parsed.metadata) <= {
        "title",
        "author",
        "subject",
        "keywords",
        "creator",
        "producer",
    }


def test_encrypted_pdf_is_rejected(parser: PyMuPDFDocumentParser) -> None:
    with pytest.raises(ParserError) as excinfo:
        parser.parse(build_encrypted_pdf())

    assert excinfo.value.code is ErrorCode.ENCRYPTED_PDF
    assert "password" in excinfo.value.message.lower()


def test_malformed_pdf_is_rejected(parser: PyMuPDFDocumentParser) -> None:
    with pytest.raises(ParserError) as excinfo:
        parser.parse(build_malformed_pdf())

    assert excinfo.value.code is ErrorCode.MALFORMED_PDF


def test_repaired_zero_page_pdf_is_rejected(parser: PyMuPDFDocumentParser) -> None:
    """PyMuPDF repairs this file into an empty document; that is still malformed."""
    with pytest.raises(ParserError) as excinfo:
        parser.parse(build_truncated_pdf())

    assert excinfo.value.code is ErrorCode.MALFORMED_PDF


def test_non_pdf_bytes_are_rejected(parser: PyMuPDFDocumentParser) -> None:
    with pytest.raises(ParserError):
        parser.parse(build_non_pdf_bytes())


def test_graphics_only_pdf_parses_but_yields_no_text(parser: PyMuPDFDocumentParser) -> None:
    """The parser reports emptiness; the no-text policy is applied above it."""
    parsed = parser.parse(build_pdf_without_text())

    assert parsed.page_count == 1
    assert parsed.character_count < 32


def test_error_messages_never_leak_internals(parser: PyMuPDFDocumentParser) -> None:
    with pytest.raises(ParserError) as excinfo:
        parser.parse(build_malformed_pdf())

    message = excinfo.value.message
    assert "Traceback" not in message
    assert "/" not in message and "\\" not in message


def test_supports_pdf_by_type_or_extension(parser: PyMuPDFDocumentParser) -> None:
    assert parser.supports(content_type="application/pdf", filename="a.bin")
    assert parser.supports(content_type="application/octet-stream", filename="a.PDF")
    assert not parser.supports(content_type="text/plain", filename="a.txt")


def test_normalisation_is_deterministic() -> None:
    """Offsets index the normalised text, so normalisation must be stable."""
    assert normalise_page_text("a\r\nb\rc") == "a\nb\nc"
    assert normalise_page_text(normalise_page_text("a\r\nb")) == normalise_page_text("a\r\nb")


def test_parsed_page_rejects_zero_page_number() -> None:
    with pytest.raises(ValueError, match="1-based"):
        ParsedPage(page_number=0, text="x")
