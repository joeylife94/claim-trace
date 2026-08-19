"""Focused tests for the first V1-04 deterministic element boundary."""

from __future__ import annotations

import uuid

import pytest

from claimtrace_api.db.models import ClaimType
from claimtrace_api.parsing.claims.base import (
    PAGE_SPAN_SEPARATOR,
    ClaimTextSpan,
    ParsedClaim,
    SourcePage,
)
from claimtrace_api.parsing.elements import (
    DeterministicElementParser,
    ElementWarningCode,
)


def _claim(
    *,
    text: str,
    spans: tuple[ClaimTextSpan, ...],
) -> ParsedClaim:
    return ParsedClaim(
        claim_number=1,
        claim_type=ClaimType.INDEPENDENT,
        spans=spans,
        text=text,
    )


def test_semicolon_elements_keep_order_and_exact_source_subspans() -> None:
    document_id = uuid.uuid4()
    page_text = "prefix 센서부; 통신부; 제어부 suffix"
    source_start = page_text.index("센서부")
    source_end = page_text.index(" suffix")
    claim_text = page_text[source_start:source_end]
    claim = _claim(
        text=claim_text,
        spans=(
            ClaimTextSpan(
                sequence_number=0,
                page_number=1,
                start_char=source_start,
                end_char=source_end,
            ),
        ),
    )

    result = DeterministicElementParser().parse(
        claim=claim,
        pages=(SourcePage(document_id=document_id, page_number=1, text=page_text),),
    )

    assert [element.sequence_number for element in result.elements] == [0, 1, 2]
    assert [element.text for element in result.elements] == ["센서부;", "통신부;", "제어부"]
    assert result.warnings == ()

    resolved = []
    for element in result.elements:
        assert len(element.spans) == 1
        span = element.spans[0]
        assert source_start <= span.start_char < span.end_char <= source_end
        resolved.append(page_text[span.start_char : span.end_char])
    assert resolved == ["센서부;", "통신부;", "제어부"]


def test_cross_page_element_omits_synthetic_separator_from_source_evidence() -> None:
    document_id = uuid.uuid4()
    first_page = "prefix 통신부는 송신기를 포함하고"
    second_page = "수신기를 포함함; 제어부 suffix"
    first_start = first_page.index("통신부")
    first_end = len(first_page)
    second_start = 0
    second_end = second_page.index(" suffix")
    first_piece = first_page[first_start:first_end]
    second_piece = second_page[second_start:second_end]
    claim_text = first_piece + PAGE_SPAN_SEPARATOR + second_piece
    claim = _claim(
        text=claim_text,
        spans=(
            ClaimTextSpan(0, 1, first_start, first_end),
            ClaimTextSpan(1, 2, second_start, second_end),
        ),
    )

    result = DeterministicElementParser().parse(
        claim=claim,
        pages=(
            SourcePage(document_id=document_id, page_number=1, text=first_page),
            SourcePage(document_id=document_id, page_number=2, text=second_page),
        ),
    )

    first_element = result.elements[0]
    assert first_element.text == first_piece + PAGE_SPAN_SEPARATOR + "수신기를 포함함;"
    assert len(first_element.spans) == 2
    assert (
        first_page[first_element.spans[0].start_char : first_element.spans[0].end_char]
        == first_piece
    )
    assert (
        second_page[first_element.spans[1].start_char : first_element.spans[1].end_char]
        == "수신기를 포함함;"
    )


def test_claim_without_explicit_delimiter_is_kept_whole_with_warning() -> None:
    document_id = uuid.uuid4()
    page_text = "센서 데이터를 수집하는 장치"
    claim = _claim(
        text=page_text,
        spans=(ClaimTextSpan(0, 1, 0, len(page_text)),),
    )

    result = DeterministicElementParser().parse(
        claim=claim,
        pages=(SourcePage(document_id=document_id, page_number=1, text=page_text),),
    )

    assert len(result.elements) == 1
    assert result.elements[0].text == page_text
    assert result.elements[0].spans[0].start_char == 0
    assert result.elements[0].spans[0].end_char == len(page_text)
    assert [warning.code for warning in result.warnings] == [
        ElementWarningCode.NO_STRUCTURAL_DELIMITER
    ]


def test_provenance_mismatch_is_rejected_instead_of_approximated() -> None:
    document_id = uuid.uuid4()
    page_text = "센서부; 통신부"
    claim = _claim(
        text="센서부; 다른텍스트",
        spans=(ClaimTextSpan(0, 1, 0, len(page_text)),),
    )

    with pytest.raises(ValueError, match="canonical source spans"):
        DeterministicElementParser().parse(
            claim=claim,
            pages=(SourcePage(document_id=document_id, page_number=1, text=page_text),),
        )
