"""PostgreSQL-backed D5 persistent analyst Case verification.

These tests verify workspace identity, references to existing documents, and the
bounded D5-02 persistence/reopen contract. They make no claim about legal
analysis, retrieval quality, or multi-user access.
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from claimtrace_api.llm.fake import FakeLLMProvider
from tests.claim_fixtures import build_korean_claims_pdf
from tests.grounded_fixtures import draft_json
from tests.pdf_factory import build_text_pdf

pytestmark = pytest.mark.integration


def _upload_document(client: TestClient, filename: str = "case-source.pdf") -> str:
    response = client.post(
        "/api/v1/documents",
        files={
            "file": (
                filename,
                build_text_pdf(
                    (
                        "기술분야\n"
                        "테스트 문서의 본문입니다. 분석 케이스가 기존 문서를 "
                        "참조하는지 검증하기 위한 충분한 길이의 공개 안전 합성 텍스트입니다.",
                    )
                ),
                "application/pdf",
            ),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload_indexed_claim_document(client: TestClient, filename: str) -> str:
    pages = (
        "【청구범위】\n"
        "【청구항 1】\n"
        "복수의 센서로부터 측정값을 수집하는 수집부와, 수집된 측정값을 저장하는 저장부를 포함하는 장치.\n"  # noqa: E501
        f"합성 문서 식별자: {filename}"
    )
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": (filename, build_korean_claims_pdf((pages,)), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]

    parsed = client.post(f"/api/v1/documents/{document_id}/claims/parse")
    assert parsed.status_code == 201, parsed.text
    indexed = client.post(f"/api/v1/documents/{document_id}/claims/index")
    assert indexed.status_code == 201, indexed.text
    return document_id


def _create_case(client: TestClient, title: str) -> str:
    created = client.post("/api/v1/cases", json={"title": title})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _associate(client: TestClient, case_id: str, document_id: str) -> None:
    associated = client.put(f"/api/v1/cases/{case_id}/documents/{document_id}")
    assert associated.status_code == 200, associated.text


def test_case_reopens_with_stable_identity_and_existing_document_reference(
    indexing_client: TestClient,
) -> None:
    document_id = _upload_document(indexing_client)

    created = indexing_client.post("/api/v1/cases", json={"title": "  Sensor review  "})
    assert created.status_code == 201, created.text
    case = created.json()
    case_id = case["id"]
    assert case["title"] == "Sensor review"
    assert case["documents"] == []

    associated = indexing_client.put(f"/api/v1/cases/{case_id}/documents/{document_id}")
    assert associated.status_code == 200, associated.text
    assert associated.json()["changed"] is True

    reopened = indexing_client.get(f"/api/v1/cases/{case_id}")
    assert reopened.status_code == 200, reopened.text
    body = reopened.json()
    assert body["id"] == case_id
    assert [document["id"] for document in body["documents"]] == [document_id]
    assert body["documents"][0]["original_filename"] == "case-source.pdf"

    source = indexing_client.get(f"/api/v1/documents/{document_id}/pages")
    assert source.status_code == 200, source.text
    assert source.json()["items"], "Case association must reference the existing source document"


def test_duplicate_association_is_explicitly_idempotent(indexing_client: TestClient) -> None:
    document_id = _upload_document(indexing_client, "duplicate-source.pdf")
    created = indexing_client.post("/api/v1/cases", json={"title": "Duplicate check"})
    case_id = created.json()["id"]

    first = indexing_client.put(f"/api/v1/cases/{case_id}/documents/{document_id}")
    second = indexing_client.put(f"/api/v1/cases/{case_id}/documents/{document_id}")

    assert first.status_code == 200
    assert first.json()["changed"] is True
    assert second.status_code == 200
    assert second.json()["changed"] is False
    assert len(second.json()["case"]["documents"]) == 1


def test_missing_references_and_disassociation_are_explicit(indexing_client: TestClient) -> None:
    created = indexing_client.post("/api/v1/cases", json={"title": "Failure contract"})
    case_id = created.json()["id"]
    missing_document_id = uuid.uuid4()

    missing = indexing_client.put(f"/api/v1/cases/{case_id}/documents/{missing_document_id}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Document not found."

    document_id = _upload_document(indexing_client, "removable-source.pdf")
    associate = indexing_client.put(f"/api/v1/cases/{case_id}/documents/{document_id}")
    assert associate.status_code == 200

    disassociate = indexing_client.delete(f"/api/v1/cases/{case_id}/documents/{document_id}")
    assert disassociate.status_code == 204

    reopened = indexing_client.get(f"/api/v1/cases/{case_id}")
    assert reopened.status_code == 200
    assert reopened.json()["documents"] == []

    duplicate_delete = indexing_client.delete(f"/api/v1/cases/{case_id}/documents/{document_id}")
    assert duplicate_delete.status_code == 404
    assert duplicate_delete.json()["detail"] == "Document is not associated with this Case."


def test_grounded_result_reopens_with_canonical_source_and_no_source_copy(
    indexing_client: TestClient,
    sync_engine: sa.Engine,
) -> None:
    document_id = _upload_indexed_claim_document(indexing_client, "case-grounded-source.pdf")
    case_id = _create_case(indexing_client, "Persistent grounded review")
    _associate(indexing_client, case_id, document_id)

    indexing_client.app.state.llm_provider = FakeLLMProvider(  # type: ignore[attr-defined]
        structured_text=draft_json([("수집부는 복수의 센서로부터 측정값을 수집한다.", ("EV-001",))])
    )
    request = {
        "query": "센서 측정값을 수집하는 구성",
        "mode": "hybrid",
        "top_k": 5,
        "document_ids": [document_id],
    }
    created = indexing_client.post(f"/api/v1/cases/{case_id}/grounded-results", json=request)
    assert created.status_code == 201, created.text
    first = created.json()
    result_id = first["id"]
    assert first["result"]["evidence"]

    reopened = indexing_client.get(f"/api/v1/cases/{case_id}/grounded-results/{result_id}")
    assert reopened.status_code == 200, reopened.text
    restored = reopened.json()
    assert restored["request"] == first["request"]
    assert restored["result"] == first["result"]

    for evidence in restored["result"]["evidence"]:
        assert evidence["document_id"] == document_id
        for span in evidence["source_spans"]:
            locator = span["locator"]
            pages = indexing_client.get(f"/api/v1/documents/{document_id}/pages?limit=200").json()[
                "items"
            ]
            page = next(item for item in pages if item["page_number"] == locator["page_number"])
            assert span["quote"] == page["text"][locator["start_char"] : locator["end_char"]]

    duplicate = indexing_client.post(f"/api/v1/cases/{case_id}/grounded-results", json=request)
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["id"] == result_id

    with sync_engine.connect() as connection:
        result_row = connection.execute(
            sa.text(
                "SELECT request_snapshot, result_snapshot FROM analyst_case_results WHERE id = :id"
            ),  # noqa: E501
            {"id": uuid.UUID(result_id)},
        ).one()
        evidence_rows = connection.execute(
            sa.text(
                "SELECT evidence_snapshot, locator_snapshot FROM analyst_case_evidence "
                "WHERE result_id = :id"
            ),
            {"id": uuid.UUID(result_id)},
        ).all()

    persisted_payload = json.dumps(
        {
            "request": result_row.request_snapshot,
            "result": result_row.result_snapshot,
            "evidence": [row.evidence_snapshot for row in evidence_rows],
            "locators": [row.locator_snapshot for row in evidence_rows],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    for evidence in first["result"]["evidence"]:
        for span in evidence["source_spans"]:
            assert span["quote"] not in persisted_payload


def test_grounded_result_rejects_cross_case_document_scope(
    indexing_client: TestClient,
) -> None:
    first_document_id = _upload_indexed_claim_document(indexing_client, "case-a.pdf")
    second_document_id = _upload_indexed_claim_document(indexing_client, "case-b.pdf")
    first_case_id = _create_case(indexing_client, "Case A")
    second_case_id = _create_case(indexing_client, "Case B")
    _associate(indexing_client, first_case_id, first_document_id)
    _associate(indexing_client, second_case_id, second_document_id)

    outside_scope = indexing_client.post(
        f"/api/v1/cases/{first_case_id}/grounded-results",
        json={
            "query": "센서 측정값",
            "mode": "hybrid",
            "top_k": 5,
            "document_ids": [second_document_id],
        },
    )
    assert outside_scope.status_code == 409
    assert "outside the Case" in outside_scope.json()["detail"]

    indexing_client.app.state.llm_provider = FakeLLMProvider(  # type: ignore[attr-defined]
        structured_text=draft_json([("수집부는 복수의 센서로부터 측정값을 수집한다.", ("EV-001",))])
    )
    created = indexing_client.post(
        f"/api/v1/cases/{first_case_id}/grounded-results",
        json={
            "query": "센서 측정값",
            "mode": "hybrid",
            "top_k": 5,
            "document_ids": [first_document_id],
        },
    )
    assert created.status_code == 201, created.text

    wrong_case_reopen = indexing_client.get(
        f"/api/v1/cases/{second_case_id}/grounded-results/{created.json()['id']}"
    )
    assert wrong_case_reopen.status_code == 404
