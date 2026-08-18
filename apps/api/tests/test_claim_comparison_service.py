"""Database-free contract tests for bounded claim comparison."""

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
from claimtrace_api.services.claim_search import SearchOutcome, SearchResult


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


def _claim(*, number: int = 1, text: str = "센서 데이터를 수집하는 통신 장치") -> Claim:
    parse_result_id = uuid.uuid4()
    claim = Claim(
        id=uuid.uuid4(),
        parse_result_id=parse_result_id,
        claim_number=number,
        claim_type=ClaimType.INDEPENDENT,
        text=text,
    )
    claim.spans = [
        ClaimSpan(
            id=uuid.uuid4(),
            claim_id=claim.id,
            sequence_number=0,
            page_number=2,
            start_char=10,
            end_char=30,
        )
    ]
    return claim


def _completed_snapshot(claim: Claim, *, dependencies: list[int] | None = None) -> object:
    return SimpleNamespace(
        result=SimpleNamespace(status=ClaimParseStatus.COMPLETED),
        claims=[claim],
        dependencies={claim.id: dependencies or []},
    )


@pytest.mark.asyncio
async def test_comparison_scopes_search_to_reference_document(settings: Settings) -> None:
    target_document_id = uuid.uuid4()
    reference_document_id = uuid.uuid4()
    target_claim = _claim()
    reference_span = ClaimSpan(
        id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        sequence_number=0,
        page_number=4,
        start_char=5,
        end_char=25,
    )
    search = FakeSearchService(
        SearchOutcome(
            mode=RetrievalMode.HYBRID,
            profile=_profile(),
            searched_index_run_count=1,
            dense_candidate_count=1,
            lexical_candidate_count=1,
            results=[
                SearchResult(
                    document_id=reference_document_id,
                    document_filename="reference.pdf",
                    claim_number=3,
                    claim_type=ClaimType.DEPENDENT,
                    text="통신 모듈을 포함하는 장치",
                    depends_on=[1],
                    spans=[reference_span],
                    fused_rank=1,
                    fused_score=0.03,
                    dense_rank=1,
                    dense_score=0.8,
                    lexical_rank=2,
                    lexical_score=0.4,
                )
            ],
        )
    )
    parsing = FakeParsingService(_completed_snapshot(target_claim, dependencies=[2]))
    service = ClaimComparisonService(
        session=FakeSession({target_document_id, reference_document_id}),  # type: ignore[arg-type]
        parsing=parsing,  # type: ignore[arg-type]
        search=search,  # type: ignore[arg-type]
        settings=settings,
    )

    outcome = await service.compare(
        target_document_id=target_document_id,
        target_claim_number=1,
        reference_document_id=reference_document_id,
        mode=RetrievalMode.HYBRID,
        top_k=5,
    )

    assert len(search.calls) == 1
    assert search.calls[0]["query"] == target_claim.text
    assert search.calls[0]["document_ids"] == [reference_document_id]
    assert outcome.target.document_id == target_document_id
    assert outcome.target.depends_on == [2]
    assert outcome.target.spans[0].page_number == 2
    assert [match.document_id for match in outcome.matches] == [reference_document_id]
    assert outcome.no_correspondence_reason is None


@pytest.mark.asyncio
async def test_comparison_refuses_scope_leak(settings: Settings) -> None:
    target_document_id = uuid.uuid4()
    reference_document_id = uuid.uuid4()
    leaked_document_id = uuid.uuid4()
    target_claim = _claim()
    search = FakeSearchService(
        SearchOutcome(
            mode=RetrievalMode.HYBRID,
            profile=_profile(),
            searched_index_run_count=1,
            dense_candidate_count=1,
            lexical_candidate_count=0,
            results=[
                SearchResult(
                    document_id=leaked_document_id,
                    document_filename="wrong.pdf",
                    claim_number=1,
                    claim_type=ClaimType.INDEPENDENT,
                    text="wrong scope",
                    depends_on=[],
                    spans=[],
                    fused_rank=1,
                    fused_score=0.02,
                )
            ],
        )
    )
    service = ClaimComparisonService(
        session=FakeSession({target_document_id, reference_document_id}),  # type: ignore[arg-type]
        parsing=FakeParsingService(_completed_snapshot(target_claim)),  # type: ignore[arg-type]
        search=search,  # type: ignore[arg-type]
        settings=settings,
    )

    with pytest.raises(AppError) as exc_info:
        await service.compare(
            target_document_id=target_document_id,
            target_claim_number=1,
            reference_document_id=reference_document_id,
            mode=RetrievalMode.HYBRID,
            top_k=5,
        )

    assert exc_info.value.code is ErrorCode.INTERNAL_ERROR


@pytest.mark.asyncio
async def test_comparison_distinguishes_unindexed_reference(settings: Settings) -> None:
    target_document_id = uuid.uuid4()
    reference_document_id = uuid.uuid4()
    target_claim = _claim()
    search = FakeSearchService(
        SearchOutcome(
            mode=RetrievalMode.HYBRID,
            profile=_profile(),
            searched_index_run_count=0,
            dense_candidate_count=0,
            lexical_candidate_count=0,
        )
    )
    service = ClaimComparisonService(
        session=FakeSession({target_document_id, reference_document_id}),  # type: ignore[arg-type]
        parsing=FakeParsingService(_completed_snapshot(target_claim)),  # type: ignore[arg-type]
        search=search,  # type: ignore[arg-type]
        settings=settings,
    )

    outcome = await service.compare(
        target_document_id=target_document_id,
        target_claim_number=1,
        reference_document_id=reference_document_id,
        mode=RetrievalMode.HYBRID,
        top_k=5,
    )

    assert outcome.matches == []
    assert outcome.no_correspondence_reason == "reference_not_indexed"


@pytest.mark.asyncio
async def test_comparison_rejects_same_document(settings: Settings) -> None:
    document_id = uuid.uuid4()
    service = ClaimComparisonService(
        session=FakeSession({document_id}),  # type: ignore[arg-type]
        parsing=FakeParsingService(None),  # type: ignore[arg-type]
        search=FakeSearchService(  # type: ignore[arg-type]
            SearchOutcome(
                mode=RetrievalMode.HYBRID,
                profile=_profile(),
                searched_index_run_count=0,
                dense_candidate_count=0,
                lexical_candidate_count=0,
            )
        ),
        settings=settings,
    )

    with pytest.raises(AppError) as exc_info:
        await service.compare(
            target_document_id=document_id,
            target_claim_number=1,
            reference_document_id=document_id,
            mode=RetrievalMode.HYBRID,
            top_k=5,
        )

    assert exc_info.value.code is ErrorCode.COMPARISON_INVALID_REQUEST
