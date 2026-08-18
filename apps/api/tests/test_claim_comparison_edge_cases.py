"""Database-free edge-state coverage for bounded claim comparison.

These tests pin the remaining response distinctions needed by V1-02 without
introducing another retrieval path: an indexed reference with zero candidates is
``no_matches``, while missing or incomplete target parse/claim state remains an
explicit error.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import Claim, ClaimParseStatus, ClaimSpan, ClaimType
from claimtrace_api.indexing.profile import IndexProfile
from claimtrace_api.retrieval.base import RetrievalMode
from claimtrace_api.services.claim_comparison import ClaimComparisonService
from claimtrace_api.services.claim_search import SearchOutcome


class FakeSession:
    def __init__(self, known_documents: set[uuid.UUID]) -> None:
        self.known_documents = known_documents

    async def get(self, _model: object, document_id: uuid.UUID) -> object | None:
        return object() if document_id in self.known_documents else None


class FakeParsingService:
    def __init__(self, snapshot: object | None) -> None:
        self._snapshot = snapshot

    async def snapshot(self, _document_id: uuid.UUID) -> object | None:
        return self._snapshot


class FakeSearchService:
    def __init__(self, outcome: SearchOutcome) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    async def search(self, **kwargs: Any) -> SearchOutcome:
        self.calls.append(kwargs)
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


def _target_claim() -> Claim:
    claim = Claim(
        id=uuid.uuid4(),
        parse_result_id=uuid.uuid4(),
        claim_number=1,
        claim_type=ClaimType.INDEPENDENT,
        text="센서 데이터를 수집하는 통신 장치",
    )
    claim.spans = [
        ClaimSpan(
            id=uuid.uuid4(),
            claim_id=claim.id,
            sequence_number=0,
            page_number=1,
            start_char=0,
            end_char=20,
        )
    ]
    return claim


def _snapshot(
    claim: Claim,
    *,
    status: ClaimParseStatus = ClaimParseStatus.COMPLETED,
) -> object:
    return SimpleNamespace(
        result=SimpleNamespace(status=status),
        claims=[claim],
        dependencies={claim.id: []},
    )


def _empty_outcome(*, searched_index_run_count: int) -> SearchOutcome:
    return SearchOutcome(
        mode=RetrievalMode.HYBRID,
        profile=_profile(),
        searched_index_run_count=searched_index_run_count,
        dense_candidate_count=0,
        lexical_candidate_count=0,
    )


def _service(
    *,
    settings: Settings,
    target_document_id: uuid.UUID,
    reference_document_id: uuid.UUID,
    snapshot: object | None,
    searched_index_run_count: int = 1,
) -> ClaimComparisonService:
    return ClaimComparisonService(
        session=FakeSession({target_document_id, reference_document_id}),  # type: ignore[arg-type]
        parsing=FakeParsingService(snapshot),  # type: ignore[arg-type]
        search=FakeSearchService(  # type: ignore[arg-type]
            _empty_outcome(searched_index_run_count=searched_index_run_count)
        ),
        settings=settings,
    )


@pytest.mark.asyncio
async def test_indexed_reference_with_zero_candidates_is_no_matches(settings: Settings) -> None:
    target_document_id = uuid.uuid4()
    reference_document_id = uuid.uuid4()
    target_claim = _target_claim()
    service = _service(
        settings=settings,
        target_document_id=target_document_id,
        reference_document_id=reference_document_id,
        snapshot=_snapshot(target_claim),
    )

    outcome = await service.compare(
        target_document_id=target_document_id,
        target_claim_number=1,
        reference_document_id=reference_document_id,
        mode=RetrievalMode.HYBRID,
        top_k=5,
    )

    assert outcome.searched_index_run_count == 1
    assert outcome.matches == []
    assert outcome.no_correspondence_reason == "no_matches"


@pytest.mark.asyncio
async def test_missing_target_parse_is_explicit(settings: Settings) -> None:
    target_document_id = uuid.uuid4()
    reference_document_id = uuid.uuid4()
    service = _service(
        settings=settings,
        target_document_id=target_document_id,
        reference_document_id=reference_document_id,
        snapshot=None,
    )

    with pytest.raises(AppError) as exc_info:
        await service.compare(
            target_document_id=target_document_id,
            target_claim_number=1,
            reference_document_id=reference_document_id,
            mode=RetrievalMode.HYBRID,
            top_k=5,
        )

    assert exc_info.value.code is ErrorCode.CLAIM_PARSE_NOT_FOUND


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        ClaimParseStatus.PROCESSING,
        ClaimParseStatus.NO_CLAIMS_FOUND,
        ClaimParseStatus.FAILED,
    ],
)
async def test_incomplete_target_parse_is_explicit(
    settings: Settings, status: ClaimParseStatus
) -> None:
    target_document_id = uuid.uuid4()
    reference_document_id = uuid.uuid4()
    service = _service(
        settings=settings,
        target_document_id=target_document_id,
        reference_document_id=reference_document_id,
        snapshot=_snapshot(_target_claim(), status=status),
    )

    with pytest.raises(AppError) as exc_info:
        await service.compare(
            target_document_id=target_document_id,
            target_claim_number=1,
            reference_document_id=reference_document_id,
            mode=RetrievalMode.HYBRID,
            top_k=5,
        )

    assert exc_info.value.code is ErrorCode.CLAIM_PARSE_NOT_COMPLETED


@pytest.mark.asyncio
async def test_missing_target_claim_is_explicit(settings: Settings) -> None:
    target_document_id = uuid.uuid4()
    reference_document_id = uuid.uuid4()
    target_claim = _target_claim()
    service = _service(
        settings=settings,
        target_document_id=target_document_id,
        reference_document_id=reference_document_id,
        snapshot=_snapshot(target_claim),
    )

    with pytest.raises(AppError) as exc_info:
        await service.compare(
            target_document_id=target_document_id,
            target_claim_number=99,
            reference_document_id=reference_document_id,
            mode=RetrievalMode.HYBRID,
            top_k=5,
        )

    assert exc_info.value.code is ErrorCode.CLAIM_NOT_FOUND
