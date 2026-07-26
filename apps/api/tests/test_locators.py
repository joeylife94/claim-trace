"""Source locator semantics.

These tests pin the contract every future citation depends on: a locator either
resolves to exactly the characters it claims, or it fails loudly.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from claimtrace_api.schemas.locators import SourceLocator

PAGE_TEXT = "A widget comprising a housing and a fastener disposed therein."
DOCUMENT_ID = uuid.uuid4()


def locator(start: int, end: int, *, page: int = 1) -> SourceLocator:
    return SourceLocator(document_id=DOCUMENT_ID, page_number=page, start_char=start, end_char=end)


def test_resolves_to_the_referenced_substring() -> None:
    span = locator(2, 8)

    assert span.resolve(PAGE_TEXT) == "widget"
    assert span.length == 6


def test_empty_span_is_valid() -> None:
    """A zero-length span is a legal insertion point, not an error."""
    assert locator(5, 5).resolve(PAGE_TEXT) == ""


def test_full_page_span_is_valid() -> None:
    assert locator(0, len(PAGE_TEXT)).resolve(PAGE_TEXT) == PAGE_TEXT


def test_span_past_the_end_is_refused() -> None:
    """Truncating instead would produce a plausible but wrong quotation."""
    with pytest.raises(ValueError, match="exceeds the page text length"):
        locator(0, len(PAGE_TEXT) + 1).resolve(PAGE_TEXT)


def test_is_within_reports_fit() -> None:
    assert locator(0, 10).is_within(len(PAGE_TEXT))
    assert not locator(0, 10).is_within(5)


def test_reversed_span_is_rejected() -> None:
    with pytest.raises(ValidationError):
        locator(10, 4)


def test_negative_offsets_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SourceLocator(document_id=DOCUMENT_ID, page_number=1, start_char=-1, end_char=4)


def test_page_numbers_are_one_based() -> None:
    with pytest.raises(ValidationError):
        locator(0, 1, page=0)


def test_locator_is_serialisable_round_trip() -> None:
    original = locator(3, 9, page=2)

    restored = SourceLocator.model_validate(original.model_dump())

    assert restored == original
    assert restored.resolve(PAGE_TEXT) == original.resolve(PAGE_TEXT)
