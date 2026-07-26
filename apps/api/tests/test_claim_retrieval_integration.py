"""Hybrid retrieval against the real schema, indexes, and SQL.

The corpus is the synthetic evaluation set - 26 newly authored Korean
patent-like claims across two documents - loaded through the real pipeline:
upload, parse, index, search. Using two documents rather than one is what makes
document scoping and cross-document ranking testable.

These tests assert *structural* properties: what is retrieved, in what order,
under which scope, and with which provenance. They deliberately do not assert
semantic quality, because they run on the deterministic embedding provider,
whose vectors are hashes rather than meaning. Semantic quality is what
``evals/`` measures, with a real model.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from claimtrace_api.indexing.embeddings.fake import FakeEmbeddingProvider
from evals.dataset import load_documents
from tests.claim_fixtures import build_korean_claims_pdf

pytestmark = pytest.mark.integration

SEARCH_URL = "/api/v1/search/claims"


@pytest.fixture
def corpus(indexing_client: TestClient) -> dict[str, str]:
    """Upload, parse, and index the whole synthetic corpus. Returns id by name."""
    document_ids: dict[str, str] = {}

    for document in load_documents():
        upload = indexing_client.post(
            "/api/v1/documents",
            files={
                "file": (
                    document.filename,
                    build_korean_claims_pdf(document.page_texts()),
                    "application/pdf",
                )
            },
        )
        assert upload.status_code == 201, upload.text
        document_id = upload.json()["id"]

        parsed = indexing_client.post(f"/api/v1/documents/{document_id}/claims/parse")
        assert parsed.status_code == 201, parsed.text
        # The corpus is only a valid fixture if the parser sees the claims the
        # dataset declares; a silent mismatch would make every label wrong.
        assert parsed.json()["result"]["claim_count"] == len(document.claims), document.id

        indexed = indexing_client.post(f"/api/v1/documents/{document_id}/claims/index")
        assert indexed.status_code == 201, indexed.text

        document_ids[document.id] = document_id

    return document_ids


def search(client: TestClient, query: str, **overrides: Any) -> Any:
    payload = {"query": query, "top_k": 10, **overrides}
    response = client.post(SEARCH_URL, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def claim_keys(body: Any) -> list[tuple[str, int]]:
    """(document filename stem, claim number) in rank order."""
    return [(result["document_filename"], result["claim_number"]) for result in body["results"]]


# -- lexical retrieval ------------------------------------------------------


def test_exact_korean_phrase_is_retrieved_first(
    corpus: dict[str, str], indexing_client: TestClient
):
    body = search(indexing_client, "순환 버퍼", mode="lexical")

    assert body["results"], "an exact phrase present in the corpus must match"
    assert body["results"][0]["claim_number"] == 4
    assert "순환 버퍼" in body["results"][0]["text"]


def test_exact_technical_number_is_retrieved(corpus: dict[str, str], indexing_client: TestClient):
    body = search(indexing_client, "섭씨 45도", mode="lexical")

    assert body["results"][0]["claim_number"] == 2
    assert "45도" in body["results"][0]["text"]


def test_full_width_digits_match_ascii_digits(corpus: dict[str, str], indexing_client: TestClient):
    """NFKC folding is applied to the query exactly as it was to the index."""
    ascii_body = search(indexing_client, "50밀리볼트", mode="lexical")
    fullwidth_body = search(indexing_client, "５０밀리볼트", mode="lexical")

    assert claim_keys(ascii_body)[:3] == claim_keys(fullwidth_body)[:3]
    assert ascii_body["results"][0]["claim_number"] == 7


def test_irregular_whitespace_does_not_change_the_result(
    corpus: dict[str, str], indexing_client: TestClient
):
    tidy = search(indexing_client, "무손실 압축 알고리즘", mode="lexical")
    messy = search(indexing_client, "  무손실   압축\n알고리즘  ", mode="lexical")

    assert claim_keys(tidy) == claim_keys(messy)


def test_a_korean_compound_written_without_spaces_still_matches(
    corpus: dict[str, str], indexing_client: TestClient
):
    """The trigram channel is what recovers this; full-text search alone cannot."""
    body = search(indexing_client, "환경감시모듈", mode="lexical")

    retrieved = {result["claim_number"] for result in body["results"]}
    assert retrieved & {7, 8, 9}, "no claim from the 환경 감시 모듈 family was retrieved"


def test_an_irrelevant_query_retrieves_nothing_lexically(
    corpus: dict[str, str], indexing_client: TestClient
):
    """Lexical search should not invent a match for vocabulary the corpus lacks."""
    body = search(indexing_client, "커피 원두 로스팅 프로파일", mode="lexical")

    assert body["results"] == []


def test_lexical_ordering_is_deterministic(corpus: dict[str, str], indexing_client: TestClient):
    runs = [claim_keys(search(indexing_client, "냉각 유로", mode="lexical")) for _ in range(3)]

    assert runs[0] == runs[1] == runs[2]


def test_lexical_scores_are_bounded_and_descending(
    corpus: dict[str, str], indexing_client: TestClient
):
    body = search(indexing_client, "배터리 셀 온도", mode="lexical")

    scores = [result["lexical_score"] for result in body["results"]]
    assert all(0.0 <= score <= 1.0 for score in scores)
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize(
    "hostile",
    [
        "'; DROP TABLE claim_search_records; --",
        "' OR 1=1 --",
        "100%",
        "_____",
        "\\",
        "센서' UNION SELECT * FROM documents --",
    ],
)
def test_sql_shaped_input_is_treated_as_text(
    corpus: dict[str, str],
    indexing_client: TestClient,
    hostile: str,
    sync_engine: sa.Engine,
):
    """Parameterised throughout, and LIKE wildcards escaped, so this is just data."""
    response = indexing_client.post(SEARCH_URL, json={"query": hostile, "mode": "lexical"})

    assert response.status_code == 200
    with sync_engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM claim_search_records")) == 26


def test_a_wildcard_query_does_not_match_everything(
    corpus: dict[str, str], indexing_client: TestClient
):
    """Unescaped, '%' in a LIKE pattern would return the entire corpus."""
    body = search(indexing_client, "%", mode="lexical")

    assert len(body["results"]) < 26


# -- dense retrieval --------------------------------------------------------


def test_dense_retrieval_returns_ranked_candidates(
    corpus: dict[str, str], indexing_client: TestClient
):
    body = search(indexing_client, "센서 데이터를 수집하는 통신 장치", mode="dense")

    assert body["results"]
    assert all(result["dense_rank"] is not None for result in body["results"])
    ranks = [result["dense_rank"] for result in body["results"]]
    assert ranks == sorted(ranks)


def test_dense_similarity_decreases_with_rank(corpus: dict[str, str], indexing_client: TestClient):
    body = search(indexing_client, "배터리 셀의 온도를 측정", mode="dense")

    scores = [result["dense_score"] for result in body["results"]]
    assert scores == sorted(scores, reverse=True)


def test_dense_ordering_is_deterministic(corpus: dict[str, str], indexing_client: TestClient):
    runs = [
        claim_keys(search(indexing_client, "냉각 팬 회전 속도", mode="dense")) for _ in range(3)
    ]

    assert runs[0] == runs[1] == runs[2]


def test_the_nearest_vector_is_the_claim_the_query_was_taken_from(
    corpus: dict[str, str], indexing_client: TestClient
):
    """With deterministic embeddings, querying a claim's own text must find it."""
    claim = next(d for d in load_documents() if d.id == "battery").claims[6]

    body = search(indexing_client, claim.text, mode="dense")

    assert body["results"][0]["claim_number"] == claim.number


def test_dense_search_excludes_records_from_an_incomplete_run(
    corpus: dict[str, str], indexing_client: TestClient, sync_engine: sa.Engine
):
    """A run that never finished must not contribute results."""
    with sync_engine.begin() as connection:
        connection.execute(sa.text("UPDATE claim_index_runs SET status = 'processing'"))

    body = search(indexing_client, "센서 데이터", mode="dense")

    assert body["searched_index_run_count"] == 0
    assert body["results"] == []


# -- profile isolation ------------------------------------------------------


def test_an_index_built_by_another_model_is_not_searched(
    corpus: dict[str, str], indexing_client: TestClient
):
    """Vectors from two models are not points in the same space."""
    before = search(indexing_client, "냉각 유로")
    assert before["results"]

    indexing_client.app.state.embedding_provider = FakeEmbeddingProvider(
        dimension=384, model="another-model", model_version="9"
    )
    after = search(indexing_client, "냉각 유로")

    assert after["searched_index_run_count"] == 0
    assert after["results"] == []
    assert after["profile"]["embedding_model"] == "another-model"


def test_reindexing_under_a_new_profile_makes_that_profile_searchable(
    corpus: dict[str, str], indexing_client: TestClient
):
    indexing_client.app.state.embedding_provider = FakeEmbeddingProvider(
        dimension=384, model_version="2"
    )
    for document_id in corpus.values():
        assert (
            indexing_client.post(f"/api/v1/documents/{document_id}/claims/index").status_code == 201
        )

    body = search(indexing_client, "냉각 유로")

    assert body["searched_index_run_count"] == 2
    assert body["results"]
    assert body["profile"]["embedding_model_version"] == "2"


# -- hybrid fusion ----------------------------------------------------------


def test_hybrid_is_the_default_mode(corpus: dict[str, str], indexing_client: TestClient):
    response = indexing_client.post(SEARCH_URL, json={"query": "센서 데이터"})

    assert response.status_code == 200
    assert response.json()["mode"] == "hybrid"


def test_hybrid_results_carry_fused_ranks_in_order(
    corpus: dict[str, str], indexing_client: TestClient
):
    body = search(indexing_client, "배터리 셀 냉각")

    assert [result["fused_rank"] for result in body["results"]] == list(
        range(1, len(body["results"]) + 1)
    )
    scores = [result["fused_score"] for result in body["results"]]
    assert scores == sorted(scores, reverse=True)


def test_hybrid_returns_each_claim_once(corpus: dict[str, str], indexing_client: TestClient):
    body = search(indexing_client, "온도 센서")

    keys = claim_keys(body)
    assert len(keys) == len(set(keys))


def test_hybrid_recalls_what_a_single_channel_misses(
    corpus: dict[str, str], indexing_client: TestClient
):
    """The point of fusing: the union is at least as complete as either channel."""
    query = "이동 평균과 표준편차"
    dense = set(claim_keys(search(indexing_client, query, mode="dense")))
    lexical = set(claim_keys(search(indexing_client, query, mode="lexical")))
    hybrid = set(claim_keys(search(indexing_client, query, mode="hybrid", top_k=50)))

    assert (dense | lexical) <= hybrid


def test_a_claim_found_by_only_one_channel_has_a_null_rank_for_the_other(
    corpus: dict[str, str], indexing_client: TestClient
):
    """Null means 'that channel did not retrieve it', which clients must render."""
    body = search(indexing_client, "커피 원두 로스팅 프로파일", top_k=10)

    assert body["results"], "dense retrieval always returns nearest neighbours"
    assert all(result["lexical_rank"] is None for result in body["results"])
    assert all(result["lexical_score"] is None for result in body["results"])
    assert all(result["dense_rank"] is not None for result in body["results"])


def test_the_rrf_constant_is_reported(corpus: dict[str, str], indexing_client: TestClient):
    body = search(indexing_client, "센서")

    assert body["profile"]["rrf_k"] == 60


# -- document scoping -------------------------------------------------------


def test_document_scope_restricts_results_to_that_document(
    corpus: dict[str, str], indexing_client: TestClient
):
    body = search(indexing_client, "온도", document_ids=[corpus["battery"]])

    assert body["results"]
    assert {result["document_id"] for result in body["results"]} == {corpus["battery"]}
    assert body["searched_index_run_count"] == 1


def test_an_unscoped_search_spans_every_document(
    corpus: dict[str, str], indexing_client: TestClient
):
    body = search(indexing_client, "온도", top_k=50)

    assert {result["document_id"] for result in body["results"]} == set(corpus.values())
    assert body["searched_index_run_count"] == 2


def test_scoping_to_an_unknown_document_returns_nothing(
    corpus: dict[str, str], indexing_client: TestClient
):
    from tests.conftest import unknown_uuid

    body = search(indexing_client, "온도", document_ids=[str(unknown_uuid())])

    assert body["searched_index_run_count"] == 0
    assert body["results"] == []


# -- provenance -------------------------------------------------------------


def test_every_result_carries_canonical_source_spans(
    corpus: dict[str, str], indexing_client: TestClient
):
    body = search(indexing_client, "배터리 열관리", top_k=10)

    assert body["results"]
    for result in body["results"]:
        assert result["source_spans"], "a result without provenance cannot be verified"
        for span in result["source_spans"]:
            assert span["document_id"] == result["document_id"]
            assert span["page_number"] >= 1
            assert 0 <= span["start_char"] < span["end_char"]


def test_every_returned_span_resolves_against_stored_page_text(
    corpus: dict[str, str], indexing_client: TestClient
):
    """The product's premise: a search result must be verifiable at its source."""
    body = search(indexing_client, "센서 데이터 수집", top_k=10)
    assert body["results"]

    pages_by_document: dict[str, dict[int, str]] = {}
    for document_id in corpus.values():
        items = indexing_client.get(f"/api/v1/documents/{document_id}/pages").json()["items"]
        pages_by_document[document_id] = {page["page_number"]: page["text"] for page in items}

    for result in body["results"]:
        pages = pages_by_document[result["document_id"]]
        resolved = [
            pages[span["page_number"]][span["start_char"] : span["end_char"]]
            for span in result["source_spans"]
        ]
        # Claim text is *defined* as its ordered spans joined by the page
        # separator, so this is an equality, not a containment check.
        assert "\n".join(resolved) == result["text"]


def test_results_return_original_claim_text_not_the_normalised_form(
    corpus: dict[str, str], indexing_client: TestClient
):
    """The normalised text is case-folded and space-collapsed; it must never leak."""
    body = search(indexing_client, "방수 등급 IP67", top_k=5)

    result = next(r for r in body["results"] if r["claim_number"] == 9)
    assert "IP67" in result["text"], "original casing must survive"


def test_dependency_references_are_returned(corpus: dict[str, str], indexing_client: TestClient):
    body = search(indexing_client, "수동 밸런싱 저항", top_k=5)

    result = next(r for r in body["results"] if r["claim_number"] == 8)
    assert result["depends_on"] == [7]


def test_independent_claims_report_no_dependencies(
    corpus: dict[str, str], indexing_client: TestClient
):
    body = search(indexing_client, "복수의 배터리 셀과 냉매를 순환시키는", top_k=10)

    result = next(
        r for r in body["results"] if r["claim_number"] == 1 and r["claim_type"] == "independent"
    )
    assert result["depends_on"] == []


# -- request validation -----------------------------------------------------


def test_an_empty_query_is_rejected(indexing_client: TestClient):
    assert indexing_client.post(SEARCH_URL, json={"query": ""}).status_code == 422


def test_a_whitespace_only_query_is_rejected(indexing_client: TestClient):
    assert indexing_client.post(SEARCH_URL, json={"query": "     "}).status_code == 422


def test_an_over_long_query_is_rejected(indexing_client: TestClient):
    response = indexing_client.post(SEARCH_URL, json={"query": "센" * 513})

    assert response.status_code == 422


def test_an_invalid_mode_is_rejected(indexing_client: TestClient):
    response = indexing_client.post(SEARCH_URL, json={"query": "센서", "mode": "magic"})

    assert response.status_code == 422


def test_an_excessive_top_k_is_rejected(indexing_client: TestClient):
    response = indexing_client.post(SEARCH_URL, json={"query": "센서", "top_k": 5000})

    assert response.status_code == 422


def test_a_non_positive_top_k_is_rejected(indexing_client: TestClient):
    assert indexing_client.post(SEARCH_URL, json={"query": "센서", "top_k": 0}).status_code == 422


def test_an_excessive_candidate_count_is_rejected(indexing_client: TestClient):
    response = indexing_client.post(
        SEARCH_URL, json={"query": "센서", "dense_candidate_count": 100_000}
    )

    assert response.status_code == 422


def test_a_malformed_document_id_is_rejected(indexing_client: TestClient):
    response = indexing_client.post(
        SEARCH_URL, json={"query": "센서", "document_ids": ["not-a-uuid"]}
    )

    assert response.status_code == 422


def test_top_k_clips_the_result_list(corpus: dict[str, str], indexing_client: TestClient):
    body = search(indexing_client, "장치", top_k=3)

    assert len(body["results"]) <= 3


# -- empty index ------------------------------------------------------------


def test_searching_before_anything_is_indexed_is_not_an_error(indexing_client: TestClient):
    """Nothing indexed and nothing matched are different states, and both are 200."""
    body = search(indexing_client, "센서 데이터")

    assert body["searched_index_run_count"] == 0
    assert body["result_count"] == 0
    assert body["profile"]["embedding_provider"] == "fake"
