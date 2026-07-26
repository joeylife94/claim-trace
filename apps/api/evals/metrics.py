"""Retrieval metrics.

Two definitions worth stating, because both are reported in a way that is easy
to misread otherwise:

* **Recall@k** here is *set recall*: the fraction of a query's relevant claims
  that appear in the top *k*. For a query with three relevant claims, Recall@1
  cannot exceed 1/3, so a low Recall@1 on this dataset is partly an artefact of
  the labels rather than a failure of retrieval.
* **MRR@10** uses the rank of the *first* relevant result, and contributes 0 when
  none appears in the top 10.

Queries with no relevant claim are excluded from both averages - there is no
meaningful recall of an empty set - and are scored separately by
:func:`false_positive_rate`, so a channel that returns something for every query
is penalised rather than ignored.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: Ranks at which recall is reported.
RECALL_AT = (1, 3, 5)
MRR_AT = 10


def recall_at_k(retrieved: Sequence[object], relevant: frozenset[object], k: int) -> float:
    """Fraction of ``relevant`` items appearing in the first ``k`` retrieved.

    Returns 0.0 for an empty relevant set: the caller is expected to exclude
    those queries, and returning 1.0 would quietly inflate every average.
    """
    if not relevant or k <= 0:
        return 0.0
    found = sum(1 for item in _dedupe(retrieved)[:k] if item in relevant)
    return found / len(relevant)


def reciprocal_rank(retrieved: Sequence[object], relevant: frozenset[object], k: int) -> float:
    """``1 / rank`` of the first relevant result within the first ``k``, else 0."""
    if not relevant or k <= 0:
        return 0.0
    for position, item in enumerate(_dedupe(retrieved)[:k], start=1):
        if item in relevant:
            return 1.0 / position
    return 0.0


def false_positive_rate(results: Sequence[Sequence[object]]) -> float:
    """Fraction of no-relevant-answer queries that still returned something.

    Retrieval always returns *something* when the corpus is non-empty, so this is
    not a defect on its own - but it is the number that stops "return everything"
    from looking like a good strategy, and it belongs in the report.
    """
    if not results:
        return 0.0
    return sum(1 for retrieved in results if retrieved) / len(results)


@dataclass(frozen=True, slots=True)
class MetricSummary:
    """Averaged metrics for one retrieval mode."""

    mode: str
    query_count: int
    #: Queries that have at least one relevant claim; the denominator of recall
    #: and MRR.
    scored_query_count: int
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr_at_10: float
    #: Of the queries labelled as having no relevant claim, the fraction for
    #: which the channel still returned at least one result.
    empty_query_hit_rate: float

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "query_count": self.query_count,
            "scored_query_count": self.scored_query_count,
            "recall_at_1": round(self.recall_at_1, 4),
            "recall_at_3": round(self.recall_at_3, 4),
            "recall_at_5": round(self.recall_at_5, 4),
            "mrr_at_10": round(self.mrr_at_10, 4),
            "empty_query_hit_rate": round(self.empty_query_hit_rate, 4),
        }


def summarise(
    mode: str,
    *,
    judged: Sequence[tuple[Sequence[object], frozenset[object]]],
) -> MetricSummary:
    """Average the metrics over ``(retrieved, relevant)`` pairs."""
    scored = [(retrieved, relevant) for retrieved, relevant in judged if relevant]
    empty = [retrieved for retrieved, relevant in judged if not relevant]

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return MetricSummary(
        mode=mode,
        query_count=len(judged),
        scored_query_count=len(scored),
        recall_at_1=mean([recall_at_k(r, rel, 1) for r, rel in scored]),
        recall_at_3=mean([recall_at_k(r, rel, 3) for r, rel in scored]),
        recall_at_5=mean([recall_at_k(r, rel, 5) for r, rel in scored]),
        mrr_at_10=mean([reciprocal_rank(r, rel, MRR_AT) for r, rel in scored]),
        empty_query_hit_rate=false_positive_rate(empty),
    )


def _dedupe(items: Sequence[object]) -> list[object]:
    """Keep first occurrences only.

    Fusion already guarantees one entry per claim; this makes the metric
    functions correct on their own terms rather than dependent on that.
    """
    seen: set[object] = set()
    unique: list[object] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique
