"""PostgreSQL-backed HTTP proof for public claim-element decomposition."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from claimtrace_api.db.models import (
    Claim,
    ClaimParseResult,
    ClaimParseStatus,
    ClaimSpan,
    ClaimType,
    Document,
    DocumentPage,
    DocumentStatus,
)

pytestmark = pytest.mark.integration


def _seed_claim(sync_engine, *, text: str) -> tuple[uuid.UUID, int]:
    document_id = uuid.uuid4()
    parse_result_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    claim_number = 1

    with Session(sync_engine) as session:
        session.add(
            Document(
                id=document_id,
                original_filename="element-api.pdf",
                content_type="application/pdf",
                size_bytes=100,
                sha256=uuid.uuid4().hex + uuid.uuid4().hex,
                storage_key=f"test/{document_id}.pdf",
                status=DocumentStatus.COMPLETED,
                page_count=1,
                extracted_character_count=len(text),
            )
        )
        session.add(
            DocumentPage(
                id=uuid.uuid4(),
                document_id=document_id,
                page_number=1,
                text=text,
                character_count=len(text),
                text_sha256="0" * 64,
            )
        )
        session.add(
            ClaimParseResult(
                id=parse_result_id,
                document_id=document_id,
                status=ClaimParseStatus.COMPLETED,
                parser_name="test-claim-parser",
                parser_version="1",
                claim_count=1,
            )
        )
        session.add(
            Claim(
                id=claim_id,
                parse_result_id=parse_result_id,
                claim_number=claim_number,
                claim_type=ClaimType.INDEPENDENT,
                text=text,
            )
        )
        session.add(
            ClaimSpan(
                id=uuid.uuid4(),
                claim_id=claim_id,
                sequence_number=0,
                page_number=1,
                start_char=0,
                end_char=len(text),
            )
        )
        session.commit()

    return document_id, claim_number


def _url(document_id: uuid.UUID, claim_number: int) -> str:
    return f"/api/v1/documents/{document_id}/claims/{claim_number}/elements/decompose"


def test_element_api_is_idempotent_and_source_backed(
    integration_client: TestClient,
    sync_engine,
) -> None:
    document_id, claim_number = _seed_claim(sync_engine, text="센서부; 통신부")

    first = integration_client.post(_url(document_id, claim_number))
    second = integration_client.post(_url(document_id, claim_number))

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    body = first.json()
    assert second.json()["id"] == body["id"]
    assert body["element_count"] == 2
    assert [element["sequence_number"] for element in body["elements"]] == [0, 1]
    assert [element["text"] for element in body["elements"]] == ["센서부;", "통신부"]
    assert body["warnings"] == []

    for element in body["elements"]:
        assert element["spans"]
        for span in element["spans"]:
            assert span["locator"]["document_id"] == str(document_id)
            assert span["locator"]["page_number"] == span["page_number"]
            assert span["locator"]["start_char"] == span["start_char"]
            assert span["locator"]["end_char"] == span["end_char"]

    forbidden = {
        "infringement",
        "validity",
        "novelty",
        "equivalence",
        "inventive_step",
        "patentability",
    }
    assert forbidden.isdisjoint(body)
    assert all(forbidden.isdisjoint(element) for element in body["elements"])


def test_element_api_exposes_resistant_shape_warning(
    integration_client: TestClient,
    sync_engine,
) -> None:
    document_id, claim_number = _seed_claim(sync_engine, text="센서 데이터를 수집하는 장치")

    response = integration_client.post(_url(document_id, claim_number))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["element_count"] == 1
    assert body["warning_count"] == 1
    assert body["warnings"][0]["code"] == "no_structural_delimiter"
    assert body["elements"][0]["text"] == "센서 데이터를 수집하는 장치"


def test_element_api_returns_explicit_missing_claim_error(
    integration_client: TestClient,
    sync_engine,
) -> None:
    document_id, _ = _seed_claim(sync_engine, text="센서부; 통신부")

    response = integration_client.post(_url(document_id, 999))

    assert response.status_code == 404, response.text
    assert response.json()["error_code"] == "claim_not_found"
