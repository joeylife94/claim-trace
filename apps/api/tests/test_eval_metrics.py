"""Evaluation metric arithmetic, and the integrity of the committed dataset.

The metrics decide what the evaluation report claims, so they are tested against
hand-computed values rather than against themselves. The dataset checks exist
because a label pointing at a claim number that does not exist would silently
depress every score with no visible error.
"""

from __future__ import annotations

import pytest

from evals.dataset import load_documents, load_queries, total_claim_count
from evals.metrics import (
    false_positive_rate,
    recall_at_k,
    reciprocal_rank,
    summarise,
)

# -- recall -----------------------------------------------------------------


def test_recall_counts_relevant_items_in_the_first_k():
    retrieved = ["a", "b", "c", "d"]
    relevant = frozenset({"b", "d"})

    assert recall_at_k(retrieved, relevant, 1) == 0.0
    assert recall_at_k(retrieved, relevant, 2) == 0.5
    assert recall_at_k(retrieved, relevant, 4) == 1.0


def test_recall_at_1_is_capped_by_the_size_of_the_relevant_set():
    """Set recall, not hit rate: three relevant claims cannot all be at rank 1."""
    assert recall_at_k(["a", "b", "c"], frozenset({"a", "b", "c"}), 1) == pytest.approx(1 / 3)


def test_recall_is_zero_when_nothing_relevant_is_retrieved():
    assert recall_at_k(["x", "y"], frozenset({"a"}), 5) == 0.0


def test_recall_of_an_empty_relevant_set_is_zero_not_one():
    """Returning 1.0 here would quietly inflate the average over no-answer queries."""
    assert recall_at_k(["a"], frozenset(), 5) == 0.0


def test_recall_of_an_empty_result_list_is_zero():
    assert recall_at_k([], frozenset({"a"}), 5) == 0.0


def test_recall_ignores_duplicates_in_the_retrieved_list():
    assert recall_at_k(["a", "a", "b"], frozenset({"a", "b"}), 2) == 1.0


def test_a_non_positive_k_yields_zero():
    assert recall_at_k(["a"], frozenset({"a"}), 0) == 0.0


# -- reciprocal rank --------------------------------------------------------


def test_reciprocal_rank_uses_the_first_relevant_position():
    assert reciprocal_rank(["x", "a", "b"], frozenset({"a", "b"}), 10) == pytest.approx(1 / 2)
    assert reciprocal_rank(["a"], frozenset({"a"}), 10) == 1.0


def test_reciprocal_rank_is_zero_beyond_the_cutoff():
    retrieved = [f"x{index}" for index in range(10)] + ["a"]

    assert reciprocal_rank(retrieved, frozenset({"a"}), 10) == 0.0
    assert reciprocal_rank(retrieved, frozenset({"a"}), 11) == pytest.approx(1 / 11)


def test_reciprocal_rank_of_an_empty_relevant_set_is_zero():
    assert reciprocal_rank(["a"], frozenset(), 10) == 0.0


def test_reciprocal_rank_ignores_duplicates():
    assert reciprocal_rank(["a", "a"], frozenset({"a"}), 10) == 1.0


# -- false positives --------------------------------------------------------


def test_false_positive_rate_counts_non_empty_result_lists():
    assert false_positive_rate([["a"], [], ["b"], []]) == 0.5
    assert false_positive_rate([[], []]) == 0.0
    assert false_positive_rate([]) == 0.0


# -- summarise --------------------------------------------------------------


def test_summarise_averages_only_over_queries_with_a_relevant_claim():
    judged = [
        (["a"], frozenset({"a"})),
        (["x"], frozenset({"b"})),
        (["z"], frozenset()),
    ]

    summary = summarise("hybrid", judged=judged)

    assert summary.query_count == 3
    assert summary.scored_query_count == 2
    assert summary.recall_at_1 == 0.5
    assert summary.mrr_at_10 == 0.5
    # The one no-answer query returned something.
    assert summary.empty_query_hit_rate == 1.0


def test_summarise_handles_a_dataset_with_no_labelled_queries():
    summary = summarise("dense", judged=[([], frozenset())])

    assert summary.scored_query_count == 0
    assert summary.recall_at_1 == 0.0
    assert summary.mrr_at_10 == 0.0


def test_summary_serialises_rounded_values():
    payload = summarise("lexical", judged=[(["a", "b", "c"], frozenset({"c"}))]).as_dict()

    assert payload["mode"] == "lexical"
    assert payload["mrr_at_10"] == pytest.approx(0.3333, abs=1e-4)


# -- dataset integrity ------------------------------------------------------


def test_the_corpus_meets_the_declared_size():
    assert total_claim_count() >= 24
    assert len(load_documents()) >= 2


def test_the_query_set_meets_the_declared_size_and_variety():
    queries = load_queries()

    assert len(queries) >= 15
    categories = {query.category for query in queries}
    assert {
        "exact_terminology",
        "korean_compound",
        "paraphrase",
        "dependency",
        "technical_number",
        "irrelevant",
    } <= categories


def test_the_dataset_includes_queries_with_no_relevant_claim():
    """Otherwise a channel that always returns something is never penalised."""
    assert any(not query.has_relevant for query in load_queries())


def test_every_relevance_label_points_at_a_claim_that_exists():
    """A stale label would depress every score with no visible error."""
    known = {
        (document.id, claim.number) for document in load_documents() for claim in document.claims
    }

    for query in load_queries():
        unknown = query.relevant - known
        assert not unknown, f"{query.id} references missing claims: {sorted(unknown)}"


def test_claim_numbers_are_unique_and_contiguous_within_each_document():
    for document in load_documents():
        numbers = [claim.number for claim in document.claims]
        assert numbers == list(range(1, len(numbers) + 1)), document.id


def test_query_ids_are_unique():
    ids = [query.id for query in load_queries()]
    assert len(ids) == len(set(ids))


def test_rendered_pages_carry_every_claim_with_a_korean_heading():
    """The corpus is only usable if the real claim parser can read it back."""
    for document in load_documents():
        rendered = "\n".join(document.page_texts())
        assert "【청구범위】" in rendered
        for claim in document.claims:
            assert f"【청구항 {claim.number}】" in rendered
            assert claim.text in rendered
