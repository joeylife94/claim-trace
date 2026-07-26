"""Reciprocal Rank Fusion.

    fused_score(claim) = Σ over channels  1 / (k + rank_in_that_channel)

RRF is used instead of a weighted sum of the raw scores because the raw scores
are not comparable. A cosine similarity of 0.82 and a lexical score of 0.74 are
numbers produced by unrelated procedures on unrelated scales; adding them, or
even min-max normalising them per query, invents a relationship that does not
exist and makes the blend depend on how tightly the day's result set happens to
be clustered. Ranks discard the magnitudes and keep only the ordering each
channel is actually entitled to assert.

``k`` (default 60, from the original Cormack et al. formulation) sets how sharply
rank 1 outweighs rank 10. A large ``k`` flattens the curve, so agreement between
channels matters more than either channel's top position; a small ``k`` makes a
single channel's first result very hard to displace.

The raw per-channel scores are carried through fusion untouched, so the API can
show why a claim ranked where it did without those numbers ever influencing the
ordering.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from claimtrace_api.retrieval.base import Candidate, FusedCandidate


def reciprocal_rank_fusion(
    *,
    dense: Sequence[Candidate] = (),
    lexical: Sequence[Candidate] = (),
    k: int = 60,
    top_k: int,
) -> list[FusedCandidate]:
    """Fuse two ranked candidate lists into one ranked list.

    Args:
        dense: Dense candidates, any order; their own ``rank`` field is used.
        lexical: Lexical candidates, likewise.
        k: The RRF constant. Must be positive.
        top_k: Maximum results to return. The list is clipped after ranking, so
            clipping never changes the order of what survives.

    Returns:
        One entry per distinct claim, ordered by descending fused score. A claim
        retrieved by both channels appears once and receives both contributions.

    Ties are broken by ascending claim number and then by claim id. Both are
    stable properties of the data rather than of the query, so the same corpus
    and query always produce the same order - which is what makes a retrieval
    regression test meaningful.
    """
    if k <= 0:
        raise ValueError("k must be positive")
    if top_k < 0:
        raise ValueError("top_k must not be negative")

    merged: dict[uuid.UUID, _Accumulator] = {}

    for candidate in dense:
        entry = merged.setdefault(candidate.claim_id, _Accumulator(candidate))
        # setdefault means a claim listed twice by one channel - which should not
        # happen, and would double-count if it did - keeps only its first entry.
        if entry.dense_rank is None:
            entry.dense_rank = candidate.rank
            entry.dense_score = candidate.score
            entry.fused_score += 1.0 / (k + candidate.rank)

    for candidate in lexical:
        entry = merged.setdefault(candidate.claim_id, _Accumulator(candidate))
        if entry.lexical_rank is None:
            entry.lexical_rank = candidate.rank
            entry.lexical_score = candidate.score
            entry.fused_score += 1.0 / (k + candidate.rank)

    ordered = sorted(
        merged.values(),
        key=lambda entry: (-entry.fused_score, entry.claim_number, str(entry.claim_id)),
    )

    return [
        FusedCandidate(
            claim_id=entry.claim_id,
            document_id=entry.document_id,
            claim_number=entry.claim_number,
            fused_rank=position,
            fused_score=entry.fused_score,
            dense_rank=entry.dense_rank,
            dense_score=entry.dense_score,
            lexical_rank=entry.lexical_rank,
            lexical_score=entry.lexical_score,
        )
        for position, entry in enumerate(ordered[:top_k], start=1)
    ]


class _Accumulator:
    """Mutable per-claim tally used while fusing. Never leaves this module."""

    __slots__ = (
        "claim_id",
        "claim_number",
        "dense_rank",
        "dense_score",
        "document_id",
        "fused_score",
        "lexical_rank",
        "lexical_score",
    )

    def __init__(self, candidate: Candidate) -> None:
        self.claim_id = candidate.claim_id
        self.document_id = candidate.document_id
        self.claim_number = candidate.claim_number
        self.fused_score = 0.0
        self.dense_rank: int | None = None
        self.dense_score: float | None = None
        self.lexical_rank: int | None = None
        self.lexical_score: float | None = None
