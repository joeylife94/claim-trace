"""PostgreSQL-backed D5-01 persistence verification.

These tests verify only workspace identity and references to existing documents.
They make no claim about legal analysis, retrieval quality, or multi-user access.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.pdf_factory import make_pdf

pytestmark = pytest.mark.integration


def _upload_document(client: TestClient, filename: str = "case-source.pdf") -> str:
    response = client.post(
        "/api/v1/documents",
        files={"file": (filename, make_pdf(["기술분야\n테스트 문서 본문입니다."]), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


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
    case_id = indexing_client.post("/api/v1/cases", json={"title": "Duplicate check"}).json()["id"]

    first = indexing_client.put(f"/api/v1/cases/{case_id}/documents/{document_id}")
    second = indexing_client.put(f"/api/v1/cases/{case_id}/documents/{document_id}")

    assert first.status_code == 200
    assert first.json()["changed"] is True
    assert second.status_code == 200
    assert second.json()["changed"] is False
    assert len(second.json()["case"]["documents"]) == 1


def test_missing_references_and_disassociation_are_explicit(indexing_client: TestClient) -> None:
    case_id = indexing_client.post("/api/v1/cases", json={"title": "Failure contract"}).json()["id"]
    missing_document_id = uuid.uuid4()

    missing = indexing_client.put(
        f"/api/v1/cases/{case_id}/documents/{missing_document_id}"
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Document not found."

    document_id = _upload_document(indexing_client, "removable-source.pdf")
    assert indexing_client.put(
        f"/api/v1/cases/{case_id}/documents/{document_id}"
    ).status_code == 200
    assert indexing_client.delete(
        f"/api/v1/cases/{case_id}/documents/{document_id}"
    ).status_code == 204

    reopened = indexing_client.get(f"/api/v1/cases/{case_id}")
    assert reopened.status_code == 200
    assert reopened.json()["documents"] == []

    duplicate_delete = indexing_client.delete(
        f"/api/v1/cases/{case_id}/documents/{document_id}"
    )
    assert duplicate_delete.status_code == 404
    assert duplicate_delete.json()["detail"] == "Document is not associated with this Case."
