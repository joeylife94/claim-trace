"""Reciprocal Rank Fusion.

Every number in these assertions is computed by hand from ``1 / (k + rank)``,
because the whole value of RRF is that the arithmetic is simple enough to verify
without trusting the implementation that produced it.
"""

from __future__ import annotations

import uuid

import pytest

from claimtrace_api.retrieval.base import Candidate
from claimtrace_api.retrieval.fusion import reciprocal_rank_fusion

DOCUMENT = uuid.UUID("11111111-1111-4111-8111-111111111111")


def candidate(claim_number: int, rank: int, score: float = 0.5) -> Candidate:
    """A candidate whose claim id is derived from its number, so ids are stable."""
    return Candidate(
        claim_id=uuid.UUID(int=claim_number),
        document_id=DOCUMENT,
        claim_number=claim_number,
        rank=rank,
        score=score,
    )


# -- single-channel candidates ----------------------------------------------


def test_a_dense_only_candidate_is_still_returned():
    """A claim one channel missed entirely must remain eligible."""
    fused = reciprocal_rank_fusion(dense=[candidate(1, rank=1)], k=60, top_k=10)

    assert len(fused) == 1
    assert fused[0].claim_number == 1
    assert fused[0].fused_score == pytest.approx(1 / 61)
    assert fused[0].dense_rank == 1
    assert fused[0].lexical_rank is None
    assert fused[0].lexical_score is None


def test_a_lexical_only_candidate_is_still_returned():
    fused = reciprocal_rank_fusion(lexical=[candidate(2, rank=1)], k=60, top_k=10)

    assert fused[0].claim_number == 2
    assert fused[0].lexical_rank == 1
    assert fused[0].dense_rank is None
    assert fused[0].dense_score is None


def test_absent_channel_scores_are_none_rather_than_zero():
    """Zero would read as 'the channel scored it badly', which is a different fact."""
    fused = reciprocal_rank_fusion(dense=[candidate(1, rank=3, score=0.9)], k=60, top_k=10)

    assert fused[0].dense_score == pytest.approx(0.9)
    assert fused[0].lexical_score is None


# -- candidates in both channels --------------------------------------------


def test_a_candidate_in_both_channels_receives_both_contributions():
    fused = reciprocal_rank_fusion(
        dense=[candidate(1, rank=2, score=0.82)],
        lexical=[candidate(1, rank=1, score=0.74)],
        k=60,
        top_k=10,
    )

    assert len(fused) == 1
    assert fused[0].fused_score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[0].dense_rank == 2
    assert fused[0].dense_score == pytest.approx(0.82)
    assert fused[0].lexical_rank == 1
    assert fused[0].lexical_score == pytest.approx(0.74)


def test_agreement_between_channels_outranks_a_single_strong_hit():
    """The reason RRF is used at all: two channels agreeing is the stronger signal."""
    fused = reciprocal_rank_fusion(
        dense=[candidate(1, rank=1), candidate(2, rank=2)],
        lexical=[candidate(2, rank=1), candidate(3, rank=2)],
        k=60,
        top_k=10,
    )

    # Claim 2 is second and first; claim 1 is first in one channel only.
    assert [result.claim_number for result in fused] == [2, 1, 3]


def test_one_result_per_claim():
    fused = reciprocal_rank_fusion(
        dense=[candidate(1, rank=1), candidate(2, rank=2)],
        lexical=[candidate(1, rank=1), candidate(2, rank=2)],
        k=60,
        top_k=10,
    )

    assert len(fused) == 2
    assert len({result.claim_number for result in fused}) == 2


def test_a_claim_listed_twice_by_one_channel_is_counted_once():
    """Double-counting would let a duplicate row silently promote a result."""
    fused = reciprocal_rank_fusion(
        dense=[candidate(1, rank=1), candidate(1, rank=5)], k=60, top_k=10
    )

    assert len(fused) == 1
    assert fused[0].fused_score == pytest.approx(1 / 61)
    assert fused[0].dense_rank == 1


# -- ordering ---------------------------------------------------------------


def test_results_are_ordered_by_descending_fused_score():
    fused = reciprocal_rank_fusion(
        dense=[candidate(7, rank=3), candidate(4, rank=1), candidate(9, rank=2)],
        k=60,
        top_k=10,
    )

    assert [result.claim_number for result in fused] == [4, 9, 7]
    assert [result.fused_rank for result in fused] == [1, 2, 3]


def test_ties_break_deterministically_by_claim_number():
    """Two claims at the same rank in different channels tie exactly."""
    fused = reciprocal_rank_fusion(
        dense=[candidate(9, rank=1)],
        lexical=[candidate(2, rank=1)],
        k=60,
        top_k=10,
    )

    assert fused[0].fused_score == pytest.approx(fused[1].fused_score)
    assert [result.claim_number for result in fused] == [2, 9]


def test_fusion_is_stable_across_input_orderings():
    """The same corpus and query must always produce the same list."""
    dense = [candidate(3, rank=2), candidate(1, rank=1)]
    lexical = [candidate(1, rank=2), candidate(5, rank=1)]

    first = reciprocal_rank_fusion(dense=dense, lexical=lexical, k=60, top_k=10)
    second = reciprocal_rank_fusion(
        dense=list(reversed(dense)), lexical=list(reversed(lexical)), k=60, top_k=10
    )

    assert [r.claim_number for r in first] == [r.claim_number for r in second]


# -- parameters -------------------------------------------------------------


def test_the_rrf_constant_is_configurable_and_changes_the_scores():
    small = reciprocal_rank_fusion(dense=[candidate(1, rank=1)], k=1, top_k=10)
    large = reciprocal_rank_fusion(dense=[candidate(1, rank=1)], k=600, top_k=10)

    assert small[0].fused_score == pytest.approx(1 / 2)
    assert large[0].fused_score == pytest.approx(1 / 601)


def test_a_small_constant_makes_a_top_hit_harder_to_displace():
    """The knob does something: with k=1 one first place beats two mid-ranks."""
    dense = [candidate(1, rank=1)]
    lexical = [candidate(2, rank=3)]
    dense_second = [candidate(2, rank=4)]

    with_small_k = reciprocal_rank_fusion(
        dense=dense + dense_second, lexical=lexical, k=1, top_k=10
    )
    with_large_k = reciprocal_rank_fusion(
        dense=dense + dense_second, lexical=lexical, k=600, top_k=10
    )

    assert with_small_k[0].claim_number == 1
    assert with_large_k[0].claim_number == 2


def test_top_k_clips_after_ranking():
    fused = reciprocal_rank_fusion(
        dense=[candidate(number, rank=number) for number in range(1, 11)], k=60, top_k=3
    )

    assert [result.claim_number for result in fused] == [1, 2, 3]
    assert [result.fused_rank for result in fused] == [1, 2, 3]


def test_top_k_of_zero_returns_nothing():
    assert reciprocal_rank_fusion(dense=[candidate(1, rank=1)], k=60, top_k=0) == []


def test_no_candidates_produces_no_results():
    assert reciprocal_rank_fusion(k=60, top_k=10) == []


def test_invalid_parameters_are_rejected():
    with pytest.raises(ValueError, match="k must be positive"):
        reciprocal_rank_fusion(dense=[candidate(1, rank=1)], k=0, top_k=10)
    with pytest.raises(ValueError, match="top_k"):
        reciprocal_rank_fusion(dense=[candidate(1, rank=1)], k=60, top_k=-1)
