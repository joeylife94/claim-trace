"""Shared retrieval types.

A candidate is deliberately thin: an identity plus the one channel's opinion of
it. Claim text, dependencies, and source spans are attached later, once fusion
has decided which claims survive, so neither channel pays to hydrate rows that
are about to be discarded.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class RetrievalMode(StrEnum):
    """Which channels contribute to a search."""

    HYBRID = "hybrid"
    DENSE = "dense"
    LEXICAL = "lexical"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One claim as returned by one retrieval channel.

    ``rank`` is 1-based and dense within the channel's own result list: it is
    what Reciprocal Rank Fusion consumes. ``score`` is kept alongside it purely
    so a reader can see *why* something ranked where it did - the two channels'
    scores are on unrelated scales and are never compared with each other.
    """

    claim_id: uuid.UUID
    document_id: uuid.UUID
    claim_number: int
    rank: int
    score: float


@dataclass(frozen=True, slots=True)
class FusedCandidate:
    """One claim after fusion, carrying whatever each channel contributed.

    A candidate found by only one channel keeps ``None`` for the other's rank and
    score. That is not missing data - it is the fact that the other channel did
    not retrieve it, which is worth showing rather than hiding behind a zero.
    """

    claim_id: uuid.UUID
    document_id: uuid.UUID
    claim_number: int
    fused_rank: int
    fused_score: float
    dense_rank: int | None = None
    dense_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
