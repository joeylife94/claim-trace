"""Regression boundary for the P11 Korean term-level lexical fallback.

These tests use the public-safe synthetic retrieval corpus and real PostgreSQL
`pg_trgm` functions. They pin the narrow eligibility contract added in P11:
a strong particle-variant term may admit a candidate when the whole multi-word
query is too weak, while a merely similar unrelated term stays below the
accepted 0.60 fallback threshold.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests.test_claim_retrieval_integration import corpus, search

pytestmark = pytest.mark.integration

_POSITIVE_QUERY = "측정값은 완전히무관한질문토큰"
_POSITIVE_TERM = "측정값은"
_NEGATIVE_QUERY = "측정가치는 완전히무관한질문토큰"
_NEGATIVE_TERM = "측정가치는"
_TERM_THRESHOLD = 0.60
_WHOLE_QUERY_THRESHOLD = 0.25


def _sensor_claim_one_signals(sync_engine: sa.Engine, *, query: str, term: str) -> dict[str, object]:
    """Measure the exact lexical gates against synthetic sensor claim 1."""
    with sync_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                """
                SELECT
                    r.normalized_text,
                    word_similarity(:query, r.normalized_text) AS whole_similarity,
                    word_similarity(:term, r.normalized_text) AS term_similarity,
                    r.search_vector @@ plainto_tsquery('simple', :term) AS fts_match,
                    r.normalized_text LIKE :phrase_pattern ESCAPE '\\' AS phrase_match
                FROM claim_search_records AS r
                WHERE r.claim_number = 1
                  AND r.normalized_text LIKE '%측정값%'
                LIMIT 1
                """
            ),
            {
                "query": query,
                "term": term,
                "phrase_pattern": f"%{query}%",
            },
        ).mappings().one()
    return dict(row)


def _sensor_claim_one_is_present(body: dict[str, object]) -> bool:
    results = body["results"]
    assert isinstance(results, list)
    return any(
        result["document_filename"] == "synthetic-sensor-collector.pdf"
        and result["claim_number"] == 1
        for result in results
    )


def test_particle_variant_term_is_the_only_eligibility_gate_for_sensor_claim_one(
    corpus: dict[str, str],
    indexing_client: TestClient,
    sync_engine: sa.Engine,
):
    signals = _sensor_claim_one_signals(
        sync_engine,
        query=_POSITIVE_QUERY,
        term=_POSITIVE_TERM,
    )

    assert signals["fts_match"] is False
    assert signals["phrase_match"] is False
    assert float(signals["whole_similarity"]) < _WHOLE_QUERY_THRESHOLD
    assert float(signals["term_similarity"]) >= _TERM_THRESHOLD

    body = search(indexing_client, _POSITIVE_QUERY, mode="lexical")
    assert _sensor_claim_one_is_present(body)


def test_weak_unrelated_term_does_not_admit_sensor_claim_one(
    corpus: dict[str, str],
    indexing_client: TestClient,
    sync_engine: sa.Engine,
):
    signals = _sensor_claim_one_signals(
        sync_engine,
        query=_NEGATIVE_QUERY,
        term=_NEGATIVE_TERM,
    )

    assert signals["fts_match"] is False
    assert signals["phrase_match"] is False
    assert float(signals["whole_similarity"]) < _WHOLE_QUERY_THRESHOLD
    assert float(signals["term_similarity"]) < _TERM_THRESHOLD

    body = search(indexing_client, _NEGATIVE_QUERY, mode="lexical")
    assert not _sensor_claim_one_is_present(body)
