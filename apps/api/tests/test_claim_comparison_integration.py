"""PostgreSQL-backed verification for bounded claim comparison.

The comparison feature deliberately reuses the existing claim retrieval stack. These
integration tests load the same synthetic two-document corpus used by retrieval tests,
then assert the property V1-02 exists to guarantee: one stored target claim may retrieve
textual correspondences only from the caller-selected reference document, and every
returned target/reference span resolves exactly against persisted page text.

The deterministic embedding provider makes these structural tests reproducible. They do
not claim semantic or legal comparison quality.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from evals.dataset import load_documents
from tests.claim_fixtures import build_korean_claims_pdf

pytestmark = pytest.mark.integration

COMPARE_URL = "/api/v1/compare/claims"


@pytest.fixture
def comparison_corpus(indexing_client: TestClient) -> dict[str, str]:
    """Upload, parse, and index the committed synthetic two-document corpus."""
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
        assert parsed.json()["result"]["claim_count"] == len(document.claims), document.id

        indexed = indexing_client.post(f"/api/v1/documents/{document_id}/claims/index")
        assert indexed.status_code == 201, indexed.text

        document_ids[document.id] = document_id

    assert set(document_ids) == {"sensor", "battery"}
    return document_ids


def compare(client: TestClient, **overrides: Any) -> Any:
    payload = {"target_claim_number": 1, "mode": "hybrid", "top_k": 10, **overrides}
    response = client.post(COMPARE_URL, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def page_texts(client: TestClient, document_id: str) -> dict[int, str]:
    response = client.get(f"/api/v1/documents/{document_id}/pages")
    assert response.status_code == 200, response.text
    return {page["page_number"]: page["text"] for page in response.json()["items"]}


def resolve_spans(pages: dict[int, str], spans: list[dict[str, Any]]) -> str:
    return "\n".join(
        pages[span["page_number"]][span["start_char"] : span["end_char"]]
        for span in spans
    )


def test_comparison_is_strictly_scoped_to_reference_document(
    comparison_corpus: dict[str, str], indexing_client: TestClient
) -> None:
    target_id = comparison_corpus["sensor"]
    reference_id = comparison_corpus["battery"]

    body = compare(
        indexing_client,
        target_document_id=target_id,
        reference_document_id=reference_id,
    )

    assert body["target"]["document_id"] == target_id
    assert body["reference_document_id"] == reference_id
    assert body["searched_index_run_count"] == 1
    assert body["matches"], "dense/hybrid retrieval over an indexed reference must return candidates"
    assert {match["document_id"] for match in body["matches"]} == {reference_id}


def test_comparison_target_and_matches_resolve_exactly_to_stored_page_text(
    comparison_corpus: dict[str, str], indexing_client: TestClient
) -> None:
    target_id = comparison_corpus["sensor"]
    reference_id = comparison_corpus["battery"]

    body = compare(
        indexing_client,
        target_document_id=target_id,
        reference_document_id=reference_id,
    )

    target_pages = page_texts(indexing_client, target_id)
    reference_pages = page_texts(indexing_client, reference_id)

    target = body["target"]
    assert target["source_spans"]
    assert resolve_spans(target_pages, target["source_spans"]) == target["text"]
    assert all(span["document_id"] == target_id for span in target["source_spans"])

    assert body["matches"]
    for match in body["matches"]:
        assert match["source_spans"], "comparison evidence without provenance is invalid"
        assert all(span["document_id"] == reference_id for span in match["source_spans"])
        assert resolve_spans(reference_pages, match["source_spans"]) == match["text"]


def test_reverse_comparison_still_respects_the_selected_reference_document(
    comparison_corpus: dict[str, str], indexing_client: TestClient
) -> None:
    target_id = comparison_corpus["battery"]
    reference_id = comparison_corpus["sensor"]

    body = compare(
        indexing_client,
        target_document_id=target_id,
        reference_document_id=reference_id,
    )

    assert body["target"]["document_id"] == target_id
    assert body["reference_document_id"] == reference_id
    assert body["matches"]
    assert {match["document_id"] for match in body["matches"]} == {reference_id}
