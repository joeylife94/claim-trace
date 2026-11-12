"""D7-01 HTTP error mapping: query-time embedding failures and malformed ids.

Every test drives a real service through the HTTP layer. Only the database edge is
stubbed, and the embedding provider is the real ``FakeEmbeddingProvider`` made to
fail, so the exception that reaches the handler is the one a real provider raises.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from claimtrace_api.api.deps import (
    get_claim_comparison_service,
    get_embedding_provider,
    get_grounded_generation_service,
    get_postgres_ready,
    get_session,
)
from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.db.models import ClaimParseStatus
from claimtrace_api.indexing.embeddings.base import EmbeddingError, EmbeddingModelUnavailable
from claimtrace_api.indexing.embeddings.fake import FakeEmbeddingProvider
from claimtrace_api.llm.fake import FakeLLMProvider
from claimtrace_api.services.case_grounded_results import CaseGroundedResultService
from claimtrace_api.services.claim_comparison import ClaimComparisonService
from claimtrace_api.services.claim_search import ClaimSearchService
from claimtrace_api.services.description_evidence import (
    DescriptionDerivationOutcome,
    DescriptionEvidenceService,
    DescriptionSegment,
)
from claimtrace_api.services.grounded_generation import GroundedGenerationService
from claimtrace_api.services.llm_generation import LLMGenerationService

#: Text that exists only on the exception chain. It must never reach a client.
CAUSE_TEXT = "secret-cache-path /srv/models/token=abc123"
UNAVAILABLE_MESSAGE = "The embedding model could not be loaded."

DOC_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
DOC_B = uuid.UUID("22222222-2222-4222-8222-222222222222")
CASE_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")


class _Result:
    """Permissive stand-in for a SQLAlchemy result: one active index run."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> int:
        return 0


class _Session:
    async def execute(self, *_args: object, **_kwargs: object) -> _Result:
        return _Result([SimpleNamespace(id=uuid.uuid4())])

    async def get(self, _model: object, _id: object) -> object:
        return object()

    async def commit(self) -> None:
        return None


def _failing(error: EmbeddingError) -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(fail_with=error)


def _unavailable() -> EmbeddingModelUnavailable:
    try:
        raise RuntimeError(CAUSE_TEXT)
    except RuntimeError as cause:
        error = EmbeddingModelUnavailable(
            ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value, UNAVAILABLE_MESSAGE
        )
        error.__cause__ = cause
        return error


@pytest.fixture
def api(app: FastAPI) -> Iterator[Callable[[EmbeddingError], TestClient]]:
    clients: list[TestClient] = []

    def build(error: EmbeddingError) -> TestClient:
        provider = _failing(error)
        app.dependency_overrides[get_postgres_ready] = lambda: True
        app.dependency_overrides[get_embedding_provider] = lambda: provider
        app.dependency_overrides[get_session] = lambda: _Session()
        # raise_server_exceptions=False: a 500 must be observed as a response,
        # not re-raised into the test.
        client = TestClient(app, raise_server_exceptions=False)
        clients.append(client)
        return client

    yield build
    app.dependency_overrides.clear()


def _assert_mapped(response: Any, *, status: int, code: ErrorCode, message: str) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert body == {"detail": message, "error_code": code.value}
    assert CAUSE_TEXT not in response.text
    assert "Traceback" not in response.text


def _comparison_service(app: FastAPI, settings: Settings) -> Callable[[], ClaimComparisonService]:
    provider = app.dependency_overrides[get_embedding_provider]()

    class _Parsing:
        async def snapshot(self, _document_id: uuid.UUID) -> object:
            return SimpleNamespace(
                result=SimpleNamespace(status=ClaimParseStatus.COMPLETED),
                claims=[SimpleNamespace(claim_number=1, text="센서 데이터를 수집하는 장치.")],
            )

    def build() -> ClaimComparisonService:
        session: Any = _Session()
        return ClaimComparisonService(
            session=session,
            parsing=_Parsing(),  # type: ignore[arg-type]
            search=ClaimSearchService(session=session, provider=provider, settings=settings),
            settings=settings,
        )

    return build


def _grounded_service(app: FastAPI, settings: Settings) -> Callable[[], GroundedGenerationService]:
    provider = app.dependency_overrides[get_embedding_provider]()

    def build() -> GroundedGenerationService:
        session: Any = _Session()
        return GroundedGenerationService(
            search=ClaimSearchService(session=session, provider=provider, settings=settings),
            llm=LLMGenerationService(provider=FakeLLMProvider(), settings=settings),
            session=session,
            settings=settings,
        )

    return build


# --------------------------------------------------------------------------
# A1: query-time embedding failure
# --------------------------------------------------------------------------


def test_claim_search_maps_unavailable_embedding_to_503(api: Any) -> None:
    client = api(_unavailable())
    response = client.post("/api/v1/search/claims", json={"query": "센서", "mode": "dense"})
    _assert_mapped(
        response,
        status=503,
        code=ErrorCode.EMBEDDING_MODEL_UNAVAILABLE,
        message=UNAVAILABLE_MESSAGE,
    )


def test_description_search_maps_unavailable_embedding_to_503(api: Any) -> None:
    client = api(_unavailable())
    response = client.post("/api/v1/search/descriptions", json={"query": "센서", "mode": "dense"})
    _assert_mapped(
        response,
        status=503,
        code=ErrorCode.EMBEDDING_MODEL_UNAVAILABLE,
        message=UNAVAILABLE_MESSAGE,
    )


def test_claim_comparison_maps_unavailable_embedding_to_503(
    app: FastAPI, settings: Settings, api: Any
) -> None:
    client = api(_unavailable())
    app.dependency_overrides[get_claim_comparison_service] = _comparison_service(app, settings)
    response = client.post(
        "/api/v1/compare/claims",
        json={
            "target_document_id": str(DOC_A),
            "target_claim_number": 1,
            "reference_document_id": str(DOC_B),
            "mode": "dense",
        },
    )
    _assert_mapped(
        response,
        status=503,
        code=ErrorCode.EMBEDDING_MODEL_UNAVAILABLE,
        message=UNAVAILABLE_MESSAGE,
    )


def test_grounded_answer_maps_unavailable_embedding_to_503(
    app: FastAPI, settings: Settings, api: Any
) -> None:
    client = api(_unavailable())
    app.dependency_overrides[get_grounded_generation_service] = _grounded_service(app, settings)
    response = client.post("/api/v1/grounded/answers", json={"query": "통신부", "mode": "dense"})
    _assert_mapped(
        response,
        status=503,
        code=ErrorCode.EMBEDDING_MODEL_UNAVAILABLE,
        message=UNAVAILABLE_MESSAGE,
    )


def test_case_grounded_result_maps_unavailable_embedding_to_503(
    app: FastAPI,
    settings: Settings,
    api: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = api(_unavailable())
    app.dependency_overrides[get_grounded_generation_service] = _grounded_service(app, settings)

    async def scope(_self: object, _case_id: uuid.UUID, requested: list[uuid.UUID]) -> list[Any]:
        return requested or [DOC_A]

    async def no_existing(_self: object, _case_id: uuid.UUID, _request: object) -> None:
        return None

    monkeypatch.setattr(CaseGroundedResultService, "scope_document_ids", scope)
    monkeypatch.setattr(CaseGroundedResultService, "find_existing", no_existing)
    response = client.post(
        f"/api/v1/cases/{CASE_ID}/grounded-results", json={"query": "통신부", "mode": "dense"}
    )
    _assert_mapped(
        response,
        status=503,
        code=ErrorCode.EMBEDDING_MODEL_UNAVAILABLE,
        message=UNAVAILABLE_MESSAGE,
    )


def test_description_indexing_maps_unavailable_embedding_to_503(
    api: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = api(_unavailable())

    async def derived(_self: object, document_id: uuid.UUID) -> DescriptionDerivationOutcome:
        segment = DescriptionSegment(
            id=uuid.uuid4(),
            document_id=document_id,
            segment_index=0,
            section_heading=None,
            page_number=1,
            start_char=0,
            end_char=10,
            text="센서 설명 문장입니다.",
        )
        return DescriptionDerivationOutcome(
            run_id=uuid.uuid4(), status="completed", segments=[segment], created=True
        )

    monkeypatch.setattr(DescriptionEvidenceService, "derive", derived)
    response = client.post(f"/api/v1/documents/{DOC_A}/descriptions/index")
    _assert_mapped(
        response,
        status=503,
        code=ErrorCode.EMBEDDING_MODEL_UNAVAILABLE,
        message=UNAVAILABLE_MESSAGE,
    )


def test_a_generic_embedding_error_maps_like_indexing_does(api: Any) -> None:
    # Indexing keeps the provider's own code and message for any EmbeddingError;
    # query time must do the same rather than collapsing it into a 500.
    client = api(EmbeddingError(ErrorCode.CLAIM_INDEX_FAILED.value, "The encoder failed."))
    response = client.post("/api/v1/search/claims", json={"query": "센서", "mode": "dense"})
    _assert_mapped(
        response, status=422, code=ErrorCode.CLAIM_INDEX_FAILED, message="The encoder failed."
    )


def test_a_dimension_mismatch_keeps_its_declared_500_code(api: Any) -> None:
    client = api(
        EmbeddingError(ErrorCode.EMBEDDING_DIMENSION_MISMATCH.value, "Width does not match.")
    )
    response = client.post("/api/v1/search/claims", json={"query": "센서", "mode": "dense"})
    _assert_mapped(
        response,
        status=500,
        code=ErrorCode.EMBEDDING_DIMENSION_MISMATCH,
        message="Width does not match.",
    )


def test_an_unrecognised_provider_code_falls_back_to_index_failed(api: Any) -> None:
    client = api(EmbeddingError("some_provider_code", "Odd failure."))
    response = client.post("/api/v1/search/claims", json={"query": "센서", "mode": "dense"})
    _assert_mapped(response, status=422, code=ErrorCode.CLAIM_INDEX_FAILED, message="Odd failure.")


def test_lexical_search_is_unaffected_by_a_failing_embedding_provider(
    api: Any,
) -> None:
    # Lexical mode never embeds, so a broken model must not turn it into an error.
    client = api(_unavailable())
    response = client.post("/api/v1/search/descriptions", json={"query": "센서", "mode": "lexical"})
    assert response.status_code != 503


def test_openapi_declares_503_on_every_route_that_can_embed(app: FastAPI) -> None:
    paths = app.openapi()["paths"]
    for path in (
        "/api/v1/search/claims",
        "/api/v1/search/descriptions",
        "/api/v1/compare/claims",
        "/api/v1/grounded/answers",
        "/api/v1/cases/{case_id}/grounded-results",
        "/api/v1/documents/{document_id}/descriptions/index",
    ):
        assert "503" in paths[path]["post"]["responses"], path


# --------------------------------------------------------------------------
# A2: malformed document id on the description routes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", ["derive", "index"])
def test_description_routes_return_422_for_a_malformed_document_id(api: Any, suffix: str) -> None:
    client = api(_unavailable())
    response = client.post(f"/api/v1/documents/not-a-uuid/descriptions/{suffix}")
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "document_id"]


def test_description_derive_still_returns_404_for_a_missing_document(api: Any) -> None:
    class _Missing(_Session):
        async def get(self, _model: object, _id: object) -> None:
            return None

    client = api(_unavailable())
    client.app.dependency_overrides[get_session] = lambda: _Missing()  # type: ignore[attr-defined]
    response = client.post(f"/api/v1/documents/{uuid.uuid4()}/descriptions/derive")
    assert response.status_code == 404
    assert response.json()["error_code"] == ErrorCode.DOCUMENT_NOT_FOUND.value


def test_description_search_rejects_a_malformed_document_ids_body_field(api: Any) -> None:
    client = api(_unavailable())
    response = client.post(
        "/api/v1/search/descriptions",
        json={"query": "센서", "document_ids": ["not-a-uuid"]},
    )
    assert response.status_code == 422
