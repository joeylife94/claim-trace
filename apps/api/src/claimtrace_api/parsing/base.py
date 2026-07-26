"""The parser contract.

A parser turns raw bytes into ordered page text and nothing else. It does not
touch the database, the filesystem, or HTTP, which is what allows a future
parser (a different PDF engine, XML, or an OCR pipeline) to be swapped in
without changing the ingestion service.

Deliberately absent: section detection, claim extraction, chunking. Those are
later phases and belong above this boundary, not inside it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from claimtrace_api.core.errors import ErrorCode


class ParserError(Exception):
    """The bytes are not a document this parser can read."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ParsedPage:
    """Text extracted from a single page.

    ``text`` is the canonical string: it is persisted verbatim, and every source
    locator's character offsets are indexes into exactly this value.
    """

    page_number: int
    text: str

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number is 1-based")

    @property
    def character_count(self) -> int:
        return len(self.text)


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Everything a parser knows about one document."""

    pages: Sequence[ParsedPage]
    parser_name: str
    parser_version: str
    #: Document-level metadata reported by the format (title, author, ...).
    #: Advisory only - never trusted for identity or provenance.
    metadata: Mapping[str, str] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def character_count(self) -> int:
        return sum(page.character_count for page in self.pages)


@runtime_checkable
class DocumentParser(Protocol):
    """Turns document bytes into ordered page text."""

    @property
    def name(self) -> str:
        """Stable identifier persisted on every document this parser handled."""

    @property
    def version(self) -> str:
        """Implementation version, persisted so a re-parse can be detected."""

    def supports(self, *, content_type: str, filename: str) -> bool:
        """Whether this parser claims the given upload."""

    def parse(self, data: bytes) -> ParsedDocument:
        """Extract ordered pages.

        Raises:
            ParserError: the bytes are unreadable, encrypted, or otherwise not
                parseable by this implementation.
        """
