"""Pure response-contract tests for bounded claim comparison."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from claimtrace_api.db.models import ClaimType
from claimtrace_api.retrieval.base import RetrievalMode
from claimtrace_api.schemas.comparison import (
    ClaimComparisonResponse,
    ComparisonClaimResponse,
    ComparisonMatchResponse,
)
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.schemas.retrieval import RetrievalProfileResponse

TARGET_DOCUMENT = uuid.uuid4()
REFERENCE_DOCUMENT = uuid.uuid4()
OTHER_DOCUMENT = uuid.uuid4()


def _profile() -> RetrievalProfileResponse:
    return RetrievalProfileResponse(
        embedding_provider="fake",
        embedding_model="fake-hash",
        embedding_model_version="1",
        embedding_dimension=384,
        vectors_normalized=True,
        normalization_version="1",
        lexical_strategy="postgres-simple-trgm",
        lexical_strategy_version="1",
        rrf_k=60,
    )


def _claim(document_id: uuid.UUID) -> ComparisonClaimResponse:
    return ComparisonClaimResponse(
        document_id=document_id,
        claim_number=1,
        claim_type=ClaimType.INDEPENDENT,
        text="센서 데이터를 수집하는 통신 장치",
        source_spans=[
            SourceLocator(
                document_id=document_id,
                page_number=1,
                start_char=0,
                end_char=20,
            )
        ],
    )


def _match(document_id: uuid.UUID = REFERENCE_DOCUMENT) -> ComparisonMatchResponse:
    return ComparisonMatchResponse(
        **_claim(document_id).model_dump(),
        fused_rank=1,
        fused_score=0.03,
    )


def _response(**overrides: object) -> ClaimComparisonResponse:
    values: dict[str, object] = {
        "target": _claim(TARGET_DOCUMENT),
        "reference_document_id": REFERENCE_DOCUMENT,
        "mode": RetrievalMode.HYBRID,
        "profile": _profile(),
        "searched_index_run_count": 1,
        "no_correspondence_found": False,
        "no_correspondence_reason": None,
        "match_count": 1,
        "matches": [_match()],
    }
    values.update(overrides)
    return ClaimComparisonResponse.model_validate(values)


def test_response_accepts_coherent_match_state() -> None:
    response = _response()

    assert response.match_count == 1
    assert response.no_correspondence_found is False


def test_response_refuses_reference_scope_leak() -> None:
    with pytest.raises(ValidationError, match="reference document"):
        _response(matches=[_match(OTHER_DOCUMENT)])


def test_response_refuses_inconsistent_match_count() -> None:
    with pytest.raises(ValidationError, match="match_count"):
        _response(match_count=2)


def test_response_requires_reason_for_empty_matches() -> None:
    with pytest.raises(ValidationError, match="no_correspondence_reason"):
        _response(
            matches=[],
            match_count=0,
            no_correspondence_found=True,
            no_correspondence_reason=None,
        )


def test_reference_not_indexed_requires_zero_searched_runs() -> None:
    with pytest.raises(ValidationError, match="zero searched index runs"):
        _response(
            matches=[],
            match_count=0,
            no_correspondence_found=True,
            no_correspondence_reason="reference_not_indexed",
            searched_index_run_count=1,
        )


def test_no_matches_requires_a_searched_index_run() -> None:
    with pytest.raises(ValidationError, match="at least one searched index run"):
        _response(
            matches=[],
            match_count=0,
            no_correspondence_found=True,
            no_correspondence_reason="no_matches",
            searched_index_run_count=0,
        )
