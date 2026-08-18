"""HTTP contract tests for bounded claim comparison."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from claimtrace_api.api.deps import get_claim_comparison_service, get_postgres_ready
from claimtrace_api.core.config import Settings
from claimtrace_api.db.models import ClaimSpan, ClaimType
from claimtrace_api.indexing.profile import IndexProfile
from claimtrace_api.retrieval.base import RetrievalMode
from claimtrace_api.services.claim_comparison import (
    ClaimComparisonOutcome,
    ComparisonTarget,
)
from claimtrace_api.services.claim_search import SearchResult

URL = "/api/v1/compare/claims"
TARGET_DOCUMENT = uuid.uuid4()
REFERENCE_DOCUMENT = uuid.uuid4()


class StubComparisonService:
    def __init__(self, outcome: ClaimComparisonOutcome) -> None:
        self.outcome = outcome

    async def compare(self, **_kwargs: object) -> ClaimComparisonOutcome:
        return self.outcome


def _profile() -> IndexProfile:
    return IndexProfile(
        embedding_provider="fake",
        embedding_model="fake-hash",
        embedding_model_version="1",
        embedding_dimension=384,
        vectors_normalized=True,
        normalization_version="1",
        lexical_strategy="postgres-simple-trgm",
        lexical_strategy_version="1",
    )


def _outcome(
    *,
    with_match: bool = True,
    no_correspondence_reason: str | None = None,
) -> ClaimComparisonOutcome:
    target_span = ClaimSpan(
        id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        sequence_number=0,
        page_number=1,
        start_char=0,
        end_char=20,
    )
    matches: list[SearchResult] = []
    if with_match:
        matches.append(
            SearchResult(
                document_id=REFERENCE_DOCUMENT,
                document_filename="reference.pdf",
                claim_number=2,
                claim_type=ClaimType.DEPENDENT,
                text="통신 모듈을 포함하는 기준 청구항",
                depends_on=[1],
                spans=[
                    ClaimSpan(
                        id=uuid.uuid4(),
                        claim_id=uuid.uuid4(),
                        sequence_number=0,
                        page_number=3,
                        start_char=12,
                        end_char=42,
                    )
                ],
                fused_rank=1,
                fused_score=0.03,
                dense_rank=1,
                dense_score=0.8,
                lexical_rank=1,
                lexical_score=0.6,
            )
        )

    reason = no_correspondence_reason
    if not with_match and reason is None:
        reason = "no_matches"

    return ClaimComparisonOutcome(
        target=ComparisonTarget(
            document_id=TARGET_DOCUMENT,
            claim_number=1,
            claim_type=ClaimType.INDEPENDENT,
            text="센서 데이터를 수집하는 통신 장치",
            depends_on=[],
            spans=(target_span,),
        ),
        reference_document_id=REFERENCE_DOCUMENT,
        mode=RetrievalMode.HYBRID,
        profile=_profile(),
        searched_index_run_count=1,
        no_correspondence_reason=reason,
        matches=matches,
    )


@pytest.fixture
def comparison_client(app: FastAPI) -> Iterator[TestClient]:
    app.dependency_overrides[get_postgres_ready] = lambda: True
    app.dependency_overrides[get_claim_comparison_service] = lambda: StubComparisonService(
        _outcome()
    )
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _payload() -> dict[str, object]:
    return {
        "target_document_id": str(TARGET_DOCUMENT),
        "target_claim_number": 1,
        "reference_document_id": str(REFERENCE_DOCUMENT),
        "mode": "hybrid",
        "top_k": 5,
    }


def _client_for_outcome(app: FastAPI, outcome: ClaimComparisonOutcome) -> TestClient:
    app.dependency_overrides[get_postgres_ready] = lambda: True
    app.dependency_overrides[get_claim_comparison_service] = lambda: StubComparisonService(outcome)
    return TestClient(app)


def test_comparison_returns_both_sides_with_source_locators(
    comparison_client: TestClient,
) -> None:
    response = comparison_client.post(URL, json=_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target"]["document_id"] == str(TARGET_DOCUMENT)
    assert body["target"]["source_spans"][0]["page_number"] == 1
    assert body["matches"][0]["document_id"] == str(REFERENCE_DOCUMENT)
    assert body["matches"][0]["source_spans"][0]["page_number"] == 3
    assert body["no_correspondence_found"] is False
    assert body["no_correspondence_reason"] is None


def test_no_matches_is_explicit_in_http_response(app: FastAPI) -> None:
    with _client_for_outcome(app, _outcome(with_match=False)) as client:
        response = client.post(URL, json=_payload())

    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matches"] == []
    assert body["match_count"] == 0
    assert body["no_correspondence_found"] is True
    assert body["no_correspondence_reason"] == "no_matches"


def test_reference_not_indexed_is_distinct_in_http_response(app: FastAPI) -> None:
    outcome = _outcome(with_match=False, no_correspondence_reason="reference_not_indexed")
    with _client_for_outcome(app, outcome) as client:
        response = client.post(URL, json=_payload())

    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matches"] == []
    assert body["match_count"] == 0
    assert body["no_correspondence_found"] is True
    assert body["no_correspondence_reason"] == "reference_not_indexed"


def test_comparison_contract_has_no_legal_conclusion_fields(
    comparison_client: TestClient,
) -> None:
    body = comparison_client.post(URL, json=_payload()).json()
    forbidden = {"infringement", "validity", "novelty", "equivalence", "patentability"}

    assert forbidden.isdisjoint(body)
    assert forbidden.isdisjoint(body["target"])
    assert all(forbidden.isdisjoint(match) for match in body["matches"])


def test_same_document_is_rejected_before_service_call(app: FastAPI) -> None:
    app.dependency_overrides[get_postgres_ready] = lambda: True
    app.dependency_overrides[get_claim_comparison_service] = lambda: StubComparisonService(
        _outcome()
    )
    payload = _payload()
    payload["reference_document_id"] = payload["target_document_id"]

    with TestClient(app) as client:
        response = client.post(URL, json=payload)

    app.dependency_overrides.clear()
    assert response.status_code == 422


def test_extra_fields_are_rejected(comparison_client: TestClient) -> None:
    payload = _payload()
    payload["equivalence"] = True

    response = comparison_client.post(URL, json=payload)

    assert response.status_code == 422
