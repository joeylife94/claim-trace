"""The claim parser contract.

A claim parser turns ordered page text into a claim graph with exact source
spans. It touches no database, no filesystem, and no HTTP. That is what lets a
second implementation - another language, another jurisdiction's conventions -
be a new class rather than a change to the service.

Deliberately absent: element decomposition, novelty or infringement reasoning,
and anything that would require a model. Phase 2B is rule-based only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from claimtrace_api.db.models import ClaimType

#: Inserted between the page spans of a claim that crosses a page break, and
#: nowhere else. Chosen because page text already uses "\n" as its only line
#: separator, so reconstruction reads like the original document.
PAGE_SPAN_SEPARATOR = "\n"


class WarningCode(StrEnum):
    """Stable codes for structural problems the parser can see but not fix.

    A warning never repairs the text. It records that something about the
    document's structure is unusual, so a reader can judge the result instead of
    trusting a silently "corrected" graph.
    """

    DUPLICATE_CLAIM_NUMBER = "duplicate_claim_number"
    EMPTY_CLAIM_BODY = "empty_claim_body"
    CLAIMS_OUT_OF_ORDER = "claims_out_of_order"
    MALFORMED_CLAIM_NUMBER = "malformed_claim_number"
    UNRESOLVED_DEPENDENCY_REFERENCE = "unresolved_dependency_reference"
    SELF_DEPENDENCY = "self_dependency"
    MALFORMED_DEPENDENCY_RANGE = "malformed_dependency_range"
    DEPENDENCY_CYCLE = "dependency_cycle"
    OVERLAPPING_CLAIM_SPANS = "overlapping_claim_spans"
    SPAN_OUT_OF_BOUNDS = "span_out_of_bounds"


class ClaimParserError(Exception):
    """The page text could not be parsed at all.

    Finding no claims is *not* this: that is a successful parse with an empty
    claim set, reported as ``no_claims_found``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class SourcePage:
    """One persisted page, exactly as stored in ``document_pages``."""

    document_id: UUID
    page_number: int
    text: str

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number is 1-based")


@dataclass(frozen=True, slots=True)
class ClaimTextSpan:
    """A half-open ``[start_char, end_char)`` range on one page.

    The same coordinate system as :class:`~claimtrace_api.schemas.locators.SourceLocator`
    - page-relative offsets into persisted page text. No flattened document
    offset exists anywhere in the parser output.
    """

    sequence_number: int
    page_number: int
    start_char: int
    end_char: int

    def __post_init__(self) -> None:
        if self.sequence_number < 0:
            raise ValueError("sequence_number must not be negative")
        if self.page_number < 1:
            raise ValueError("page_number is 1-based")
        if self.start_char < 0:
            raise ValueError("start_char must not be negative")
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")

    @property
    def length(self) -> int:
        return self.end_char - self.start_char

    def resolve(self, page_text: str) -> str:
        """Return the referenced substring, or raise if the span does not fit."""
        if self.end_char > len(page_text):
            raise ValueError("claim span exceeds the page text length")
        return page_text[self.start_char : self.end_char]


@dataclass(frozen=True, slots=True)
class ParseWarning:
    """One structural problem, tied to a claim number where one is known."""

    code: WarningCode
    message: str
    claim_number: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "claim_number": self.claim_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedClaim:
    """One claim: its number, classification, exact source, and resolved references."""

    claim_number: int
    claim_type: ClaimType
    spans: tuple[ClaimTextSpan, ...]
    #: Reconstructed by joining the ordered spans with PAGE_SPAN_SEPARATOR.
    text: str
    #: Claim numbers this claim explicitly references, resolved within this
    #: document, de-duplicated, ascending. Unresolved references are warnings.
    dependencies: tuple[int, ...] = ()

    @property
    def crosses_pages(self) -> bool:
        return len({span.page_number for span in self.spans}) > 1


@dataclass(frozen=True, slots=True)
class ParsedClaimSet:
    """Everything a claim parser found in one document."""

    claims: tuple[ParsedClaim, ...]
    parser_name: str
    parser_version: str
    warnings: tuple[ParseWarning, ...] = field(default_factory=tuple)

    @property
    def claim_count(self) -> int:
        return len(self.claims)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def dependency_count(self) -> int:
        return sum(len(claim.dependencies) for claim in self.claims)

    @property
    def is_empty(self) -> bool:
        return not self.claims


@runtime_checkable
class ClaimParser(Protocol):
    """Extracts claim structure from ordered page text."""

    @property
    def name(self) -> str:
        """Stable identifier persisted on every parse result."""

    @property
    def version(self) -> str:
        """Implementation version. Part of the parse result's identity."""

    def parse(self, pages: Sequence[SourcePage]) -> ParsedClaimSet:
        """Extract the claim graph.

        Raises:
            ClaimParserError: the pages could not be parsed. Finding no claims is
                not an error - it returns an empty claim set.
        """
