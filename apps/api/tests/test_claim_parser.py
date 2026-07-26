"""Deterministic Korean claim parser behaviour.

These tests pin the parsing rules themselves: what counts as a heading, what
counts as a dependency, and what the parser refuses to guess at.
"""

from __future__ import annotations

import pytest

from claimtrace_api.db.models import ClaimType
from claimtrace_api.parsing.claims.base import (
    PAGE_SPAN_SEPARATOR,
    ClaimParserError,
    ClaimTextSpan,
    ParsedClaim,
    SourcePage,
    WarningCode,
)
from claimtrace_api.parsing.claims.korean_rules import (
    KoreanRuleBasedClaimParser,
    reconstruct_text,
    validate_spans,
)
from tests.claim_fixtures import KOREAN_CLAIM_SET, NON_PATENT_TEXT, pages


@pytest.fixture
def parser() -> KoreanRuleBasedClaimParser:
    return KoreanRuleBasedClaimParser()


def numbers(result: object) -> list[int]:
    return [claim.claim_number for claim in result.claims]  # type: ignore[attr-defined]


def warning_codes(result: object) -> list[str]:
    return [warning.code.value for warning in result.warnings]  # type: ignore[attr-defined]


# -- headings ---------------------------------------------------------------


def test_single_independent_claim(parser: KoreanRuleBasedClaimParser) -> None:
    result = parser.parse(pages("【청구항 1】\n하우징을 포함하는 위젯 장치."))

    assert result.claim_count == 1
    claim = result.claims[0]
    assert claim.claim_number == 1
    assert claim.claim_type is ClaimType.INDEPENDENT
    assert claim.dependencies == ()
    assert claim.text == "하우징을 포함하는 위젯 장치."


def test_independent_then_dependent_claims(parser: KoreanRuleBasedClaimParser) -> None:
    result = parser.parse(pages(KOREAN_CLAIM_SET))

    assert numbers(result) == [1, 2, 3, 4]
    assert [claim.claim_type for claim in result.claims] == [
        ClaimType.INDEPENDENT,
        ClaimType.DEPENDENT,
        ClaimType.MULTIPLE_DEPENDENT,
        ClaimType.MULTIPLE_DEPENDENT,
    ]
    assert result.warnings == ()


@pytest.mark.parametrize(
    "heading",
    [
        "청구항 1",
        "청구항 제1항",
        "[청구항 1]",
        "【청구항 1】",
        "〔청구항 1〕",
        "청구항 1.",
        "청구항　1".replace("　", " "),
    ],
)
def test_heading_variants(parser: KoreanRuleBasedClaimParser, heading: str) -> None:
    result = parser.parse(pages(f"{heading}\n하우징을 포함하는 위젯 장치."))

    assert numbers(result) == [1]
    assert result.claims[0].text == "하우징을 포함하는 위젯 장치."


def test_fullwidth_digits_in_heading(parser: KoreanRuleBasedClaimParser) -> None:
    """Full-width digits appear in some filings and must not shift offsets."""
    result = parser.parse(pages("【청구항 １】\n하우징을 포함하는 위젯 장치."))

    assert numbers(result) == [1]


def test_english_fallback_heading(parser: KoreanRuleBasedClaimParser) -> None:
    result = parser.parse(pages("Claim 1\nA widget comprising a housing.\n"))

    assert numbers(result) == [1]
    assert result.claims[0].claim_type is ClaimType.INDEPENDENT


def test_english_fallback_does_not_match_prose(parser: KoreanRuleBasedClaimParser) -> None:
    """The English form is line-anchored, so prose mentioning a claim is ignored."""
    result = parser.parse(pages("As described in Claim 1 above, the widget is durable.\n"))

    assert result.is_empty


def test_line_initial_reference_is_not_a_heading(parser: KoreanRuleBasedClaimParser) -> None:
    """ "청구항 1에 있어서" starting a line is a reference, not claim 1's heading."""
    text = (
        "【청구항 1】\n하우징을 포함하는 위젯 장치.\n"
        "【청구항 2】\n청구항 1에 있어서, 금속인 위젯 장치.\n"
    )

    result = parser.parse(pages(text))

    assert numbers(result) == [1, 2]
    assert result.claims[1].dependencies == (1,)


def test_claims_region_excludes_the_abstract(parser: KoreanRuleBasedClaimParser) -> None:
    text = KOREAN_CLAIM_SET + "【요약서】\n본 요약은 청구항이 아니며 파싱 대상이 아니다.\n"

    result = parser.parse(pages(text))

    assert numbers(result) == [1, 2, 3, 4]
    assert "요약" not in result.claims[-1].text


# -- dependencies -----------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("제1항에 있어서, 금속인 장치.", (1,)),
        ("청구항 1에 있어서, 금속인 장치.", (1,)),
        ("제1항에 따른 장치로서, 금속인 장치.", (1,)),
        ("청구항 1에 따른 장치로서, 금속인 장치.", (1,)),
        ("제1항에 기재된 장치로서, 금속인 장치.", (1,)),
    ],
)
def test_single_dependency_forms(
    parser: KoreanRuleBasedClaimParser, body: str, expected: tuple[int, ...]
) -> None:
    text = f"【청구항 1】\n하우징을 포함하는 장치.\n【청구항 2】\n{body}\n"

    result = parser.parse(pages(text))

    assert result.claims[1].dependencies == expected
    assert result.claims[1].claim_type is ClaimType.DEPENDENT


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("제1항 또는 제2항에 있어서, 금속인 장치.", (1, 2)),
        ("제1항 및 제2항에 있어서, 금속인 장치.", (1, 2)),
        ("제1항, 제2항에 있어서, 금속인 장치.", (1, 2)),
        ("제1항 내지 제3항 중 어느 한 항에 있어서, 금속인 장치.", (1, 2, 3)),
        ("청구항 1 또는 청구항 2에 있어서, 금속인 장치.", (1, 2)),
    ],
)
def test_multiple_dependency_forms(
    parser: KoreanRuleBasedClaimParser, body: str, expected: tuple[int, ...]
) -> None:
    text = (
        "【청구항 1】\n하우징.\n【청구항 2】\n제1항에 있어서, 샤프트.\n"
        "【청구항 3】\n제1항에 있어서, 커버.\n"
        f"【청구항 4】\n{body}\n"
    )

    result = parser.parse(pages(text))

    claim = result.claims[-1]
    assert claim.dependencies == expected
    assert claim.claim_type is ClaimType.MULTIPLE_DEPENDENT


def test_range_dependency_expands_every_member(parser: KoreanRuleBasedClaimParser) -> None:
    text = (
        "【청구항 1】\n가.\n"
        "【청구항 2】\n제1항에 있어서, 나.\n"
        "【청구항 3】\n제1항에 있어서, 다.\n"
        "【청구항 4】\n제1항에 있어서, 라.\n"
        "【청구항 5】\n제2항 내지 제4항 중 어느 한 항에 있어서, 마.\n"
    )

    result = parser.parse(pages(text))

    assert result.claims[-1].dependencies == (2, 3, 4)


def test_technical_numbers_are_not_dependencies(parser: KoreanRuleBasedClaimParser) -> None:
    """A number without a claim-reference form and particle is just data."""
    text = (
        "【청구항 1】\n온도 100도, 압력 3바, 길이 5mm, 도 2에 도시된 3개의 부재를 포함하는 장치.\n"
    )

    result = parser.parse(pages(text))

    assert result.claims[0].dependencies == ()
    assert result.claims[0].claim_type is ClaimType.INDEPENDENT


def test_bare_claim_number_without_particle_is_not_a_dependency(
    parser: KoreanRuleBasedClaimParser,
) -> None:
    text = "【청구항 1】\n가.\n【청구항 2】\n제1항 및 본 명세서의 설명을 참조하는 장치.\n"

    result = parser.parse(pages(text))

    assert result.claims[1].dependencies == ()
    assert result.claims[1].claim_type is ClaimType.INDEPENDENT


def test_unresolved_reference_is_reported_not_fabricated(
    parser: KoreanRuleBasedClaimParser,
) -> None:
    text = "【청구항 1】\n가.\n【청구항 2】\n제9항에 있어서, 나.\n"

    result = parser.parse(pages(text))

    claim = result.claims[1]
    assert claim.dependencies == ()
    assert claim.claim_type is ClaimType.UNKNOWN
    assert WarningCode.UNRESOLVED_DEPENDENCY_REFERENCE.value in warning_codes(result)


def test_self_dependency_is_rejected(parser: KoreanRuleBasedClaimParser) -> None:
    text = "【청구항 1】\n가.\n【청구항 2】\n제2항에 있어서, 나.\n"

    result = parser.parse(pages(text))

    claim = result.claims[1]
    assert claim.dependencies == ()
    assert claim.claim_type is ClaimType.UNKNOWN
    assert WarningCode.SELF_DEPENDENCY.value in warning_codes(result)


def test_cycle_is_detected_and_reported(parser: KoreanRuleBasedClaimParser) -> None:
    """Claims cannot legitimately form a cycle, so it is surfaced as a warning."""
    text = "【청구항 1】\n제2항에 있어서, 가.\n【청구항 2】\n제1항에 있어서, 나.\n"

    result = parser.parse(pages(text))

    assert WarningCode.DEPENDENCY_CYCLE.value in warning_codes(result)
    # The edges are still recorded: the database preserves the real graph.
    assert result.claims[0].dependencies == (2,)
    assert result.claims[1].dependencies == (1,)


def test_backwards_range_is_discarded_with_a_warning(
    parser: KoreanRuleBasedClaimParser,
) -> None:
    text = (
        "【청구항 1】\n가.\n"
        "【청구항 2】\n제1항에 있어서, 나.\n"
        "【청구항 3】\n제2항 내지 제1항에 있어서, 다.\n"
    )

    result = parser.parse(pages(text))

    assert WarningCode.MALFORMED_DEPENDENCY_RANGE.value in warning_codes(result)
    assert result.claims[2].dependencies == (2,)


# -- structural problems ----------------------------------------------------


def test_no_claims_found_is_not_an_error(parser: KoreanRuleBasedClaimParser) -> None:
    result = parser.parse(pages(NON_PATENT_TEXT))

    assert result.is_empty
    assert result.claim_count == 0


def test_duplicate_claim_number_keeps_the_first(parser: KoreanRuleBasedClaimParser) -> None:
    text = "【청구항 1】\n최초 본문.\n【청구항 1】\n중복 본문.\n"

    result = parser.parse(pages(text))

    assert numbers(result) == [1]
    assert result.claims[0].text == "최초 본문."
    assert WarningCode.DUPLICATE_CLAIM_NUMBER.value in warning_codes(result)


def test_out_of_order_headings_warn_but_still_parse(
    parser: KoreanRuleBasedClaimParser,
) -> None:
    text = "【청구항 2】\n가.\n【청구항 1】\n나.\n"

    result = parser.parse(pages(text))

    assert numbers(result) == [1, 2]
    assert WarningCode.CLAIMS_OUT_OF_ORDER.value in warning_codes(result)


def test_claim_number_gaps_are_allowed(parser: KoreanRuleBasedClaimParser) -> None:
    text = "【청구항 1】\n가.\n【청구항 5】\n제1항에 있어서, 나.\n"

    result = parser.parse(pages(text))

    assert numbers(result) == [1, 5]
    assert result.warnings == ()


def test_empty_claim_body_is_reported_and_dropped(
    parser: KoreanRuleBasedClaimParser,
) -> None:
    text = "【청구항 1】\n\n【청구항 2】\n실제 본문이 있는 청구항.\n"

    result = parser.parse(pages(text))

    assert numbers(result) == [2]
    assert WarningCode.EMPTY_CLAIM_BODY.value in warning_codes(result)


# -- spans and provenance ---------------------------------------------------


def test_span_offsets_address_the_persisted_page_exactly(
    parser: KoreanRuleBasedClaimParser,
) -> None:
    page_text = "【청구항 1】\n하우징을 포함하는 위젯 장치.\n"

    result = parser.parse(pages(page_text))

    span = result.claims[0].spans[0]
    assert span.page_number == 1
    assert page_text[span.start_char : span.end_char] == "하우징을 포함하는 위젯 장치."
    assert span.resolve(page_text) == result.claims[0].text


def test_claim_spanning_two_pages_produces_two_ordered_spans(
    parser: KoreanRuleBasedClaimParser,
) -> None:
    first = "【청구항 1】\n하우징과, 상기 하우징의 내부에 배치되는"
    second = " 체결구를 포함하는 위젯 장치.\n"

    result = parser.parse(pages(first, second))

    claim = result.claims[0]
    assert claim.crosses_pages
    assert [span.sequence_number for span in claim.spans] == [0, 1]
    assert [span.page_number for span in claim.spans] == [1, 2]
    assert claim.spans[0].start_char == len("【청구항 1】\n")
    assert claim.spans[0].end_char == len(first)
    # Interior whitespace belongs to the claim: only the outer edges are trimmed,
    # so page 2's span starts at its very first character.
    assert claim.spans[1].start_char == 0
    assert claim.spans[1].resolve(second) == second.rstrip("\n")


def test_page_crossing_text_is_the_ordered_spans_joined_by_the_separator(
    parser: KoreanRuleBasedClaimParser,
) -> None:
    first = "【청구항 1】\n앞부분 본문"
    second = "뒷부분 본문.\n"
    source = pages(first, second)

    result = parser.parse(source)

    claim = result.claims[0]
    page_text = {page.page_number: page.text for page in source}
    expected = PAGE_SPAN_SEPARATOR.join(
        span.resolve(page_text[span.page_number]) for span in claim.spans
    )
    assert claim.text == expected
    assert claim.text == "앞부분 본문" + PAGE_SPAN_SEPARATOR + "뒷부분 본문."


def test_claim_starting_at_a_page_boundary(parser: KoreanRuleBasedClaimParser) -> None:
    """A heading as the first thing on a page still yields a page-2 span."""
    result = parser.parse(pages("【청구항 1】\n가.\n", "【청구항 2】\n제1항에 있어서, 나.\n"))

    assert numbers(result) == [1, 2]
    second = result.claims[1]
    assert [span.page_number for span in second.spans] == [2]
    assert second.spans[0].start_char == len("【청구항 2】\n")


def test_second_claim_body_does_not_include_the_next_heading(
    parser: KoreanRuleBasedClaimParser,
) -> None:
    result = parser.parse(pages(KOREAN_CLAIM_SET))

    assert all("청구항" not in claim.text.split("에 있어서")[0][:8] for claim in result.claims)
    assert "【청구항" not in result.claims[0].text


def test_spans_of_different_claims_never_overlap(
    parser: KoreanRuleBasedClaimParser,
) -> None:
    result = parser.parse(pages(KOREAN_CLAIM_SET))

    intervals = sorted(
        (span.start_char, span.end_char)
        for claim in result.claims
        for span in claim.spans
        if span.page_number == 1
    )
    for (_, previous_end), (start, _) in zip(intervals, intervals[1:], strict=False):
        assert start >= previous_end


# -- validators -------------------------------------------------------------


def test_validate_spans_rejects_out_of_bounds_offsets() -> None:
    source = [SourcePage(document_id=pages("x")[0].document_id, page_number=1, text="short")]
    claim = ParsedClaim(
        claim_number=1,
        claim_type=ClaimType.INDEPENDENT,
        spans=(ClaimTextSpan(sequence_number=0, page_number=1, start_char=0, end_char=99),),
        text="short",
    )

    with pytest.raises(ClaimParserError, match="outside page"):
        validate_spans([claim], source)


def test_validate_spans_detects_overlapping_claims() -> None:
    source = pages("0123456789")
    first = ParsedClaim(
        claim_number=1,
        claim_type=ClaimType.INDEPENDENT,
        spans=(ClaimTextSpan(sequence_number=0, page_number=1, start_char=0, end_char=6),),
        text="012345",
    )
    second = ParsedClaim(
        claim_number=2,
        claim_type=ClaimType.INDEPENDENT,
        spans=(ClaimTextSpan(sequence_number=0, page_number=1, start_char=4, end_char=9),),
        text="45678",
    )

    with pytest.raises(ClaimParserError, match="overlapping"):
        validate_spans([first, second], source)


def test_reconstruct_text_refuses_a_missing_page() -> None:
    span = ClaimTextSpan(sequence_number=0, page_number=7, start_char=0, end_char=3)

    with pytest.raises(ClaimParserError, match="missing page"):
        reconstruct_text([span], {1: "abc"})


def test_span_rejects_an_empty_range() -> None:
    with pytest.raises(ValueError, match="greater than start_char"):
        ClaimTextSpan(sequence_number=0, page_number=1, start_char=5, end_char=5)


def test_parser_identity_is_stable(parser: KoreanRuleBasedClaimParser) -> None:
    result = parser.parse(pages(KOREAN_CLAIM_SET))

    assert result.parser_name == "korean-rule-based-claims"
    assert result.parser_version == "0.1.0"
    assert parser.name == result.parser_name


def test_parsing_is_deterministic(parser: KoreanRuleBasedClaimParser) -> None:
    source = pages(KOREAN_CLAIM_SET)

    first = parser.parse(source)
    second = parser.parse(source)

    assert first == second
