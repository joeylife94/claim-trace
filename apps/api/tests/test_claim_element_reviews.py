"""PostgreSQL/API proof for append-only human review of decomposition runs."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from claimtrace_api.db.element_models import (
    ClaimElement,
    ClaimElementSpan,
    ElementDecompositionRun,
)
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
from claimtrace_api.db.review_models import ElementDecompositionReview

pytestmark = pytest.mark.integration


def _seed_reviewable_run(engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    document_id = uuid.uuid4()
    parse_result_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    run_id = uuid.uuid4()
    element_id = uuid.uuid4()
    text = "센서부; 통신부"

    with Session(engine) as session:
        session.add(
            Document(
                id=document_id,
                original_filename="review.pdf",
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
                claim_number=1,
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

        session.add(
            ElementDecompositionRun(
                id=run_id,
                claim_id=claim_id,
                parser_name="deterministic-semicolon-elements",
                parser_version="1",
                element_count=1,
                warning_count=0,
                warnings=[],
            )
        )
        session.commit()
        session.add(
            ClaimElement(
                id=element_id,
                run_id=run_id,
                sequence_number=0,
                text="센서부;",
            )
        )
        session.commit()
        session.add(
            ClaimElementSpan(
                id=uuid.uuid4(),
                element_id=element_id,
                sequence_number=0,
                page_number=1,
                start_char=0,
                end_char=4,
            )
        )
        session.commit()

    return document_id, claim_id, run_id


def _machine_snapshot(engine: Engine, run_id: uuid.UUID) -> tuple[object, ...]:
    with Session(engine) as session:
        run = session.get(ElementDecompositionRun, run_id)
        assert run is not None
        elements = session.scalars(
            select(ClaimElement)
            .where(ClaimElement.run_id == run_id)
            .order_by(ClaimElement.sequence_number)
        ).all()
        spans = session.scalars(
            select(ClaimElementSpan)
            .join(ClaimElement, ClaimElement.id == ClaimElementSpan.element_id)
            .where(ClaimElement.run_id == run_id)
            .order_by(ClaimElementSpan.sequence_number)
        ).all()
        return (
            run.claim_id,
            run.parser_name,
            run.parser_version,
            tuple((item.id, item.sequence_number, item.text) for item in elements),
            tuple(
                (
                    item.id,
                    item.element_id,
                    item.sequence_number,
                    item.page_number,
                    item.start_char,
                    item.end_char,
                )
                for item in spans
            ),
        )


def _url(run_id: uuid.UUID) -> str:
    return f"/api/v1/element-decomposition-runs/{run_id}/reviews"


def test_review_history_is_append_only_source_backed_and_survives_new_run(
    integration_client: TestClient,
    sync_engine: Engine,
) -> None:
    document_id, claim_id, run_id = _seed_reviewable_run(sync_engine)
    before = _machine_snapshot(sync_engine, run_id)

    accepted = integration_client.post(_url(run_id), json={"status": "accepted"})
    correction = integration_client.post(_url(run_id), json={"status": "needs_correction"})

    assert accepted.status_code == 201, accepted.text
    assert correction.status_code == 201, correction.text
    body = correction.json()
    assert body["run_id"] == str(run_id)
    assert body["claim_id"] == str(claim_id)
    assert body["document_id"] == str(document_id)
    assert body["parser_version"] == "1"
    assert [review["status"] for review in body["reviews"]] == [
        "accepted",
        "needs_correction",
    ]
    assert body["elements"][0]["text"] == "센서부;"
    assert body["elements"][0]["spans"][0]["locator"] == {
        "document_id": str(document_id),
        "page_number": 1,
        "start_char": 0,
        "end_char": 4,
    }

    with Session(sync_engine) as session:
        session.add(
            ElementDecompositionRun(
                id=uuid.uuid4(),
                claim_id=claim_id,
                parser_name="deterministic-semicolon-elements",
                parser_version="2",
                element_count=0,
                warning_count=1,
                warnings=[{"code": "future_parser", "message": "version two"}],
            )
        )
        session.commit()

    after = _machine_snapshot(sync_engine, run_id)
    assert after == before

    fetched = integration_client.get(_url(run_id))
    assert fetched.status_code == 200, fetched.text
    fetched_body = fetched.json()
    assert fetched_body["run_id"] == str(run_id)
    assert fetched_body["parser_version"] == "1"
    assert [review["status"] for review in fetched_body["reviews"]] == [
        "accepted",
        "needs_correction",
    ]

    with Session(sync_engine) as session:
        reviews = session.scalars(
            select(ElementDecompositionReview).order_by(ElementDecompositionReview.created_at)
        ).all()
        assert len(reviews) == 2
        assert {review.run_id for review in reviews} == {run_id}

    forbidden = {
        "infringement",
        "validity",
        "novelty",
        "equivalence",
        "inventive_step",
        "patentability",
    }
    assert forbidden.isdisjoint(fetched_body)
    assert all(forbidden.isdisjoint(review) for review in fetched_body["reviews"])


def test_review_api_rejects_invalid_state_and_missing_run(
    integration_client: TestClient,
) -> None:
    run_id = uuid.uuid4()

    invalid = integration_client.post(_url(run_id), json={"status": "approved"})
    assert invalid.status_code == 422, invalid.text

    missing = integration_client.get(_url(run_id))
    assert missing.status_code == 404, missing.text
    assert missing.json()["error_code"] == "element_decomposition_run_not_found"
