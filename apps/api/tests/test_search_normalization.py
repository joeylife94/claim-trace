"""The normalised search representation.

The property that matters most here is the last one: normalisation must never
touch the source text, because the source text is what every citation resolves
against.
"""

from __future__ import annotations

from claimtrace_api.db.models import ClaimType
from claimtrace_api.indexing.normalization import (
    build_search_text,
    normalize_search_text,
    query_terms,
)

# -- normalize_search_text --------------------------------------------------


def test_nfkc_folds_compatibility_forms():
    """Full-width Latin and the compatibility Hangul block fold to canonical forms."""
    assert normalize_search_text("ＡＢＣ") == "abc"


def test_full_width_digits_become_ascii():
    """１００도 and 100도 must be the same string, or a query for one misses the other."""
    assert normalize_search_text("동작 온도 １００도") == normalize_search_text("동작 온도 100도")
    assert normalize_search_text("１２３") == "123"


def test_line_endings_are_normalised_before_whitespace_collapsing():
    """A claim reconstructed on Windows must match the same claim from Linux."""
    assert normalize_search_text("하우징과\r\n체결구") == "하우징과 체결구"
    assert normalize_search_text("하우징과\r체결구") == "하우징과 체결구"


def test_whitespace_runs_collapse_including_the_ideographic_space():
    """U+3000 survives NFKC, so the whitespace pass has to catch it separately."""
    assert normalize_search_text("센서   데이터") == "센서 데이터"
    assert normalize_search_text("센서　데이터") == "센서 데이터"
    assert normalize_search_text("  앞뒤 공백  ") == "앞뒤 공백"


def test_latin_text_is_case_folded():
    assert normalize_search_text("Widget APPARATUS") == "widget apparatus"


def test_punctuation_is_preserved():
    """Decimals and hyphenated part numbers are exactly what a patent search needs."""
    assert "0.5" in normalize_search_text("두께 0.5mm")
    assert "a-1" in normalize_search_text("부재 A-1")
    assert "제1항" in normalize_search_text("제1항에 있어서,")


def test_normalisation_is_idempotent():
    """Applying it twice must not drift, or the index and the query could diverge."""
    once = normalize_search_text("【청구항 １】  하우징과\r\n체결구")
    assert normalize_search_text(once) == once


def test_empty_and_whitespace_only_input():
    assert normalize_search_text("") == ""
    assert normalize_search_text("   \n\t ") == ""


def test_source_text_is_never_mutated():
    """The guarantee the whole citation model rests on."""
    original = "【청구항 １】\r\n하우징과   체결구를 포함하는 장치."
    kept = str(original)

    normalize_search_text(original)
    build_search_text(
        claim_number=1, claim_type=ClaimType.INDEPENDENT, dependencies=[], body=original
    )

    assert original == kept


# -- build_search_text ------------------------------------------------------


def test_search_text_carries_number_type_and_body():
    text = build_search_text(
        claim_number=3,
        claim_type=ClaimType.INDEPENDENT,
        dependencies=[],
        body="하우징을 포함하는 장치.",
    )

    assert "청구항 3" in text
    assert "독립항" in text
    assert "하우징을 포함하는 장치." in text


def test_search_text_records_dependency_references_in_ascending_order():
    """A dependent claim's body does not always name its parents tokenisably."""
    text = build_search_text(
        claim_number=4,
        claim_type=ClaimType.MULTIPLE_DEPENDENT,
        dependencies=[3, 1, 2],
        body="금속 재질인 장치.",
    )

    assert "다중종속항" in text
    assert "인용 제1항 제2항 제3항" in text


def test_search_text_is_deterministic():
    arguments = {
        "claim_number": 2,
        "claim_type": ClaimType.DEPENDENT,
        "dependencies": [1],
        "body": "제1항에 있어서, 나사산을 갖는 장치.",
    }
    assert build_search_text(**arguments) == build_search_text(**arguments)


def test_search_text_preserves_the_whole_claim_body():
    """Nothing is truncated: what was indexed has to be what the document says."""
    body = "하우징과, " + "매우 긴 구성요소 설명, " * 40 + "체결구를 포함하는 장치."

    text = build_search_text(
        claim_number=1, claim_type=ClaimType.INDEPENDENT, dependencies=[], body=body
    )

    assert normalize_search_text(body) in text


def test_each_claim_type_has_a_distinct_token():
    tokens = {
        build_search_text(
            claim_number=1, claim_type=claim_type, dependencies=[], body="장치."
        ).split(" ")[2]
        for claim_type in ClaimType
    }
    assert len(tokens) == len(ClaimType)


# -- query_terms ------------------------------------------------------------


def test_query_terms_normalise_consistently_with_indexed_text():
    """The terms sent as parameters must line up with the stored lexemes."""
    assert query_terms("센서   데이터") == ["센서", "데이터"]
    assert query_terms("１００도") == ["100도"]


def test_query_terms_are_bounded():
    """Without a cap a pathological query would build a tsquery with thousands of branches."""
    assert len(query_terms(" ".join(str(index) for index in range(500)))) == 32


def test_blank_query_has_no_terms():
    assert query_terms("") == []
    assert query_terms("    ") == []
