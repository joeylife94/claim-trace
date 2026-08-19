"""Deterministic, provenance-preserving claim element decomposition.

This module is intentionally smaller than a legal claim-construction engine. It
recognises only explicit semicolon separators in the persisted claim text. When
that conservative signal is absent it returns one source-backed element plus a
warning rather than inventing structure.

Every returned element span is a half-open page-relative sub-span of an existing
claim span. Synthetic page separators used to reconstruct cross-page claim text
are never returned as source evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from claimtrace_api.parsing.claims.base import (
    PAGE_SPAN_SEPARATOR,
    ClaimTextSpan,
    ParsedClaim,
    SourcePage,
)

PARSER_NAME = "deterministic-semicolon-elements"
PARSER_VERSION = "1"


class ElementWarningCode(StrEnum):
    """Stable warnings for bounded decomposition outcomes."""

    NO_STRUCTURAL_DELIMITER = "no_structural_delimiter"
    EMPTY_SEGMENT = "empty_segment"


@dataclass(frozen=True, slots=True)
class ElementWarning:
    code: ElementWarningCode
    message: str


@dataclass(frozen=True, slots=True)
class ElementSourceSpan:
    """One exact persisted source range belonging to an element."""

    page_number: int
    start_char: int
    end_char: int

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number is 1-based")
        if self.start_char < 0:
            raise ValueError("start_char must not be negative")
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")


@dataclass(frozen=True, slots=True)
class DecomposedElement:
    """One ordered textual element with exact claim-contained provenance."""

    sequence_number: int
    text: str
    spans: tuple[ElementSourceSpan, ...]

    def __post_init__(self) -> None:
        if self.sequence_number < 0:
            raise ValueError("sequence_number must not be negative")
        if not self.text:
            raise ValueError("element text must not be empty")
        if not self.spans:
            raise ValueError("an element must cite at least one source span")


@dataclass(frozen=True, slots=True)
class ElementDecomposition:
    """Pure decomposition result; persistence and human review live elsewhere."""

    claim_number: int
    parser_name: str
    parser_version: str
    elements: tuple[DecomposedElement, ...]
    warnings: tuple[ElementWarning, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class _SourceChunk:
    """Mapping from reconstructed claim offsets back to one persisted page span."""

    flat_start: int
    flat_end: int
    page_number: int
    source_start: int


class DeterministicElementParser:
    """Conservative semicolon-based element parser.

    Semicolons are explicit textual structure that can be mapped without semantic
    inference. More ambitious Korean claim grammar belongs in later parser
    versions and must keep the same provenance guarantees.
    """

    name = PARSER_NAME
    version = PARSER_VERSION

    def parse(
        self,
        *,
        claim: ParsedClaim,
        pages: Sequence[SourcePage],
    ) -> ElementDecomposition:
        page_text = {page.page_number: page.text for page in pages}
        reconstructed, chunks = _reconstruct_claim(claim.spans, page_text)
        if reconstructed != claim.text:
            raise ValueError("claim text does not match its canonical source spans")

        ranges, warnings = _element_ranges(claim.text)
        elements = tuple(
            DecomposedElement(
                sequence_number=index,
                text=claim.text[start:end],
                spans=_map_range_to_source(start, end, chunks),
            )
            for index, (start, end) in enumerate(ranges)
        )
        return ElementDecomposition(
            claim_number=claim.claim_number,
            parser_name=self.name,
            parser_version=self.version,
            elements=elements,
            warnings=warnings,
        )


def _reconstruct_claim(
    spans: Sequence[ClaimTextSpan],
    page_text: dict[int, str],
) -> tuple[str, tuple[_SourceChunk, ...]]:
    ordered = sorted(spans, key=lambda span: span.sequence_number)
    parts: list[str] = []
    chunks: list[_SourceChunk] = []
    flat_offset = 0

    for index, span in enumerate(ordered):
        try:
            text = span.resolve(page_text[span.page_number])
        except KeyError as exc:
            raise ValueError(f"source page {span.page_number} is missing") from exc

        parts.append(text)
        chunks.append(
            _SourceChunk(
                flat_start=flat_offset,
                flat_end=flat_offset + len(text),
                page_number=span.page_number,
                source_start=span.start_char,
            )
        )
        flat_offset += len(text)
        if index < len(ordered) - 1:
            parts.append(PAGE_SPAN_SEPARATOR)
            flat_offset += len(PAGE_SPAN_SEPARATOR)

    return "".join(parts), tuple(chunks)


def _element_ranges(
    text: str,
) -> tuple[tuple[tuple[int, int], ...], tuple[ElementWarning, ...]]:
    warnings: list[ElementWarning] = []
    if ";" not in text:
        start, end = _trim_range(text, 0, len(text))
        if start == end:
            return (), (
                ElementWarning(
                    code=ElementWarningCode.EMPTY_SEGMENT,
                    message="The claim contains no non-whitespace text to decompose.",
                ),
            )
        return ((start, end),), (
            ElementWarning(
                code=ElementWarningCode.NO_STRUCTURAL_DELIMITER,
                message=(
                    "No explicit semicolon boundary was found; the claim is kept as one "
                    "reviewable element instead of inferring additional structure."
                ),
            ),
        )

    ranges: list[tuple[int, int]] = []
    cursor = 0
    for index, character in enumerate(text):
        if character != ";":
            continue
        payload_start, payload_end = _trim_range(text, cursor, index)
        if payload_start < payload_end:
            ranges.append((payload_start, index + 1))
        else:
            warnings.append(
                ElementWarning(
                    code=ElementWarningCode.EMPTY_SEGMENT,
                    message="An empty semicolon-delimited segment was ignored.",
                )
            )
        cursor = index + 1

    start, end = _trim_range(text, cursor, len(text))
    if start < end:
        ranges.append((start, end))
    elif cursor < len(text):
        warnings.append(
            ElementWarning(
                code=ElementWarningCode.EMPTY_SEGMENT,
                message="An empty trailing segment was ignored.",
            )
        )

    return tuple(ranges), tuple(warnings)


def _trim_range(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _map_range_to_source(
    start: int,
    end: int,
    chunks: Sequence[_SourceChunk],
) -> tuple[ElementSourceSpan, ...]:
    spans: list[ElementSourceSpan] = []
    for chunk in chunks:
        overlap_start = max(start, chunk.flat_start)
        overlap_end = min(end, chunk.flat_end)
        if overlap_start >= overlap_end:
            continue
        spans.append(
            ElementSourceSpan(
                page_number=chunk.page_number,
                start_char=chunk.source_start + overlap_start - chunk.flat_start,
                end_char=chunk.source_start + overlap_end - chunk.flat_start,
            )
        )

    if not spans:
        raise ValueError("element range does not resolve to persisted claim source")
    return tuple(spans)
