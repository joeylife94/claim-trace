"""The LLM diagnostics HTTP surface.

Exercised through the real application with a fake provider injected at the
dependency seam, so routing, request validation, error mapping, and response
serialisation all run for real. No test here needs a model server.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from claimtrace_api.api.deps import get_llm_provider, get_postgres_ready
from claimtrace_api.core.config import Settings
from claimtrace_api.llm.errors import (
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMTimeoutError,
    LLMUnsupportedCapabilityError,
)
from claimtrace_api.llm.fake import FakeLLMProvider
from claimtrace_api.main import create_app

STATUS_URL = "/api/v1/llm/status"
GENERATE_URL = "/api/v1/llm/diagnostics/generate"
STRUCTURED_URL = "/api/v1/llm/diagnostics/structured"


def build_client(
    provider: FakeLLMProvider | None = None, **overrides: object
) -> Iterator[TestClient]:
    values: dict[str, object] = {
        "environment": "development",
        "database_url": "postgresql+psycopg://unused:unused@localhost:5432/unused",
        "llm_provider": "fake",
        "embedding_provider": "fake",
    }
    values.update(overrides)
    settings = Settings(**values)  # type: ignore[arg-type]
    app: FastAPI = create_app(settings)
    app.dependency_overrides[get_postgres_ready] = lambda: True
    if provider is not None:
        app.dependency_overrides[get_llm_provider] = lambda: provider
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from build_client()


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------


def test_status_reports_a_healthy_provider(client: TestClient):
    body = client.get(STATUS_URL).json()

    assert body["provider"] == "fake"
    assert body["configured"] is True
    assert body["available"] is True
    assert body["model_available"] is True
    assert body["capabilities"]["structured_output_mode"] == "native_json_schema"
    assert body["capabilities"]["supports_streaming"] is False


def test_status_stays_200_when_the_provider_is_unreachable():
    """An unavailable model server is what this endpoint exists to report."""
    for client in build_client(FakeLLMProvider(healthy=False)):
        response = client.get(STATUS_URL)

        assert response.status_code == 200
        assert response.json()["available"] is False
        assert response.json()["error_code"] == "llm_provider_unavailable"


def test_status_distinguishes_a_reachable_server_from_an_available_model():
    for client in build_client(FakeLLMProvider(model_available=False)):
        body = client.get(STATUS_URL).json()

        assert body["available"] is True
        assert body["model_available"] is False


def test_status_exposes_no_secrets():
    for client in build_client(
        llm_provider="openai_compatible",
        llm_openai_compatible_base_url="http://user:sk-secret@localhost:8000/v1",
        llm_openai_compatible_api_key="sk-another-secret",
    ):
        raw = client.get(STATUS_URL).text

        assert "sk-secret" not in raw
        assert "sk-another-secret" not in raw
        assert "user:" not in raw


def test_status_reports_the_configured_bounds(client: TestClient):
    body = client.get(STATUS_URL).json()

    assert body["timeouts"]["max_seconds"] == 180.0
    assert body["max_prompt_characters"] == 8000
    assert body["retry_max_attempts"] == 2


def test_health_does_not_depend_on_the_llm():
    """Liveness must not follow a model server down."""
    for client in build_client(FakeLLMProvider(healthy=False)):
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200


# --------------------------------------------------------------------------
# Diagnostics gating
# --------------------------------------------------------------------------


def test_diagnostics_are_disabled_by_default_outside_development():
    for client in build_client(environment="staging"):
        response = client.post(GENERATE_URL, json={"prompt": "질문"})

        assert response.status_code == 404
        assert response.json()["error_code"] == "llm_diagnostics_disabled"


def test_diagnostics_can_be_disabled_explicitly_in_development():
    for client in build_client(llm_diagnostics_enabled=False):
        assert client.post(GENERATE_URL, json={"prompt": "질문"}).status_code == 404
        assert client.post(STRUCTURED_URL, json={"prompt": "질문"}).status_code == 404
        # Status stays available: it is how an operator sees they are off.
        assert client.get(STATUS_URL).json()["diagnostics_enabled"] is False


def test_diagnostics_can_be_enabled_explicitly_outside_development():
    for client in build_client(environment="staging", llm_diagnostics_enabled=True):
        assert client.post(GENERATE_URL, json={"prompt": "질문"}).status_code == 200


# --------------------------------------------------------------------------
# Plain generation
# --------------------------------------------------------------------------


def test_plain_generation_returns_text_and_metadata():
    for client in build_client(FakeLLMProvider(text="생성된 응답")):
        body = client.post(GENERATE_URL, json={"prompt": "질문"}).json()

        assert body["text"] == "생성된 응답"
        assert body["metadata"]["provider"] == "fake"
        assert body["metadata"]["finish_reason"] == "stop"
        assert body["metadata"]["usage"]["total_tokens"] is not None
        assert body["metadata"]["attempts"] == 1


def test_a_system_instruction_is_accepted(client: TestClient):
    response = client.post(GENERATE_URL, json={"prompt": "질문", "system": "간결하게 답하세요."})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"prompt": ""},
        {"prompt": "   "},
        {"prompt": "질문", "temperature": 2.5},
        {"prompt": "질문", "temperature": -1},
        {"prompt": "질문", "max_output_tokens": 0},
        {"prompt": "질문", "max_output_tokens": 99999},
        {"prompt": "질문", "timeout_seconds": 0},
        {"prompt": "질문", "timeout_seconds": 10_000},
    ],
)
def test_invalid_requests_are_rejected(client: TestClient, payload: dict[str, object]):
    assert client.post(GENERATE_URL, json=payload).status_code == 422


def test_an_excessive_prompt_is_rejected(client: TestClient):
    response = client.post(GENERATE_URL, json={"prompt": "가" * 9000})
    assert response.status_code == 422


def test_the_prompt_limit_can_be_lowered_by_configuration():
    """The schema ceiling is absolute; settings may tighten it further."""
    for client in build_client(llm_max_prompt_characters=50):
        response = client.post(GENERATE_URL, json={"prompt": "가" * 100})

        assert response.status_code == 400
        assert response.json()["error_code"] == "llm_invalid_request"


def test_the_model_cannot_be_overridden_by_a_request(client: TestClient):
    """An unknown field is refused outright rather than ignored."""
    response = client.post(GENERATE_URL, json={"prompt": "질문", "model": "llama3.1:8b"})
    assert response.status_code == 422


def test_the_provider_cannot_be_overridden_by_a_request(client: TestClient):
    response = client.post(GENERATE_URL, json={"prompt": "질문", "provider": "openai_compatible"})
    assert response.status_code == 422


def test_the_base_url_cannot_be_injected_by_a_request(client: TestClient):
    response = client.post(
        GENERATE_URL, json={"prompt": "질문", "base_url": "http://attacker.example.com"}
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Structured generation
# --------------------------------------------------------------------------


def test_structured_generation_returns_a_validated_result():
    for client in build_client():
        body = client.post(STRUCTURED_URL, json={"prompt": "이 문장을 요약해줘"}).json()

        assert set(body["result"]) == {"title", "keywords", "confidence"}
        assert isinstance(body["result"]["keywords"], list)
        assert 0.0 <= body["result"]["confidence"] <= 1.0
        assert body["metadata"]["structured_output_mode"] == "native_json_schema"


def test_a_schema_violation_is_reported_as_such():
    provider = FakeLLMProvider(structured_text='{"title": "제목"}')

    for client in build_client(provider):
        response = client.post(STRUCTURED_URL, json={"prompt": "요약"})

        assert response.status_code == 422
        assert response.json()["error_code"] == "llm_structured_output_validation_failed"


def test_malformed_model_output_is_reported_as_such():
    provider = FakeLLMProvider(structured_text="죄송하지만 도와드릴 수 없습니다")

    for client in build_client(provider):
        response = client.post(STRUCTURED_URL, json={"prompt": "요약"})

        assert response.status_code == 502
        assert response.json()["error_code"] == "llm_malformed_json"


def test_the_raw_model_output_is_not_echoed_back():
    """The one place unvalidated model text could reach a client verbatim."""
    provider = FakeLLMProvider(
        structured_text='{"title": "제목", "keywords": [], "confidence": 0.5}'
    )
    for client in build_client(provider):
        body = client.post(STRUCTURED_URL, json={"prompt": "요약"}).json()

        assert "text" not in body
        assert "raw" not in body


def test_no_caller_supplied_schema_is_accepted(client: TestClient):
    response = client.post(
        STRUCTURED_URL,
        json={"prompt": "요약", "schema": {"type": "object", "properties": {}}},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Provider failure mapping
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (LLMProviderUnavailableError("down"), 503, "llm_provider_unavailable"),
        (LLMModelNotFoundError("missing"), 503, "llm_model_not_found"),
        (LLMTimeoutError("slow"), 504, "llm_request_timeout"),
        (LLMUnsupportedCapabilityError("no"), 501, "llm_unsupported_capability"),
    ],
)
def test_provider_failures_map_to_documented_statuses(error: Exception, status: int, code: str):
    for client in build_client(FakeLLMProvider(fail_with=error)):  # type: ignore[arg-type]
        response = client.post(GENERATE_URL, json={"prompt": "질문"})

        assert response.status_code == status
        assert response.json()["error_code"] == code


def test_an_error_response_carries_a_code_and_a_safe_message():
    provider = FakeLLMProvider(fail_with=LLMModelNotFoundError("qwen2.5 is not installed"))

    for client in build_client(provider):
        body = client.post(GENERATE_URL, json={"prompt": "기밀 청구항 본문"}).json()

        assert body["error_code"] == "llm_model_not_found"
        assert "기밀" not in body["detail"]
        assert "Traceback" not in body["detail"]


def test_the_endpoints_are_documented_in_the_openapi_schema(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]

    assert STATUS_URL in paths
    assert GENERATE_URL in paths
    assert STRUCTURED_URL in paths
