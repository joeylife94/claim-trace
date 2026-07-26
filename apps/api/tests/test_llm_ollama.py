"""Ollama adapter contract tests.

Run against ``httpx.MockTransport``, so the real request is built, serialised,
and routed by httpx - only the socket is replaced. No test here needs Ollama
installed or a model downloaded; the live validation is recorded in
``docs/ARCHITECTURE.md`` instead.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import BaseModel, Field

from claimtrace_api.llm.errors import (
    LLMAuthenticationError,
    LLMContextLengthExceededError,
    LLMInternalProviderError,
    LLMInvalidRequestError,
    LLMInvalidResponseError,
    LLMMalformedJSONError,
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMRateLimitedError,
    LLMTimeoutError,
)
from claimtrace_api.llm.models import (
    FinishReason,
    GenerationOptions,
    GenerationRequest,
    Message,
    MessageRole,
    StructuredOutputMode,
)
from claimtrace_api.llm.ollama import OllamaProvider
from claimtrace_api.llm.retry import RetryPolicy
from tests.conftest import capture_logs

BASE_URL = "http://ollama:11434"
MODEL = "qwen2.5:1.5b"

Handler = Callable[[httpx.Request], httpx.Response]


class Summary(BaseModel):
    title: str
    keywords: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


def chat_body(content: str, **overrides: object) -> dict[str, object]:
    """A realistic non-streaming /api/chat response."""
    body: dict[str, object] = {
        "model": MODEL,
        "created_at": "2026-07-26T00:00:00Z",
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": "stop",
        "total_duration": 1_500_000_000,
        "load_duration": 500_000_000,
        "prompt_eval_count": 26,
        "eval_count": 42,
    }
    body.update(overrides)
    return body


def tags_body(*names: str) -> dict[str, object]:
    return {
        "models": [
            {"name": name, "model": name, "size": 986_000_000, "digest": "65ec06548149abcd"}
            for name in names
        ]
    }


def provider(handler: Handler, *, retry_policy: RetryPolicy | None = None) -> OllamaProvider:
    """An adapter wired to a mock transport.

    Retries are off by default so an error-mapping test asserts one request
    rather than a retried pair; the retry tests pass an explicit policy.
    """
    client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return OllamaProvider(
        base_url=BASE_URL,
        model=MODEL,
        client=client,
        retry_policy=retry_policy or RetryPolicy(max_attempts=1),
    )


def request(content: str = "질문", **options: object) -> GenerationRequest:
    return GenerationRequest(
        messages=(Message(role=MessageRole.USER, content=content),),
        options=GenerationOptions(**options),  # type: ignore[arg-type]
    )


def responder(body: dict[str, object], status: int = 200) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


# --------------------------------------------------------------------------
# Health and model availability
# --------------------------------------------------------------------------


async def test_health_reports_reachable_with_the_model_installed():
    status = await provider(responder(tags_body(MODEL))).check_health()

    assert status.available is True
    assert status.model_available is True


async def test_health_distinguishes_a_missing_model_from_an_unreachable_server():
    status = await provider(responder(tags_body("llama3.1:8b"))).check_health()

    assert status.available is True
    assert status.model_available is False
    assert status.error_code == "llm_model_not_found"
    # The remedy belongs in the message: this is the most common setup mistake.
    assert f"ollama pull {MODEL}" in status.detail


async def test_health_reports_an_unreachable_server_without_raising():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    status = await provider(handler).check_health()

    assert status.available is False
    assert status.model_available is False
    assert status.error_code == "llm_connection_error"


async def test_a_bare_model_name_matches_the_latest_tag():
    """`ollama pull qwen2.5` installs `qwen2.5:latest`; that must not read as missing."""
    client = httpx.AsyncClient(
        base_url=BASE_URL, transport=httpx.MockTransport(responder(tags_body("qwen2.5:latest")))
    )
    bare = OllamaProvider(base_url=BASE_URL, model="qwen2.5", client=client)

    assert (await bare.check_health()).model_available is True


async def test_health_records_the_digest_as_the_model_version():
    """The tag is mutable; the digest identifies the weights that answered."""
    instance = provider(responder(tags_body(MODEL)))
    await instance.check_health()

    assert instance.get_metadata().model_version == "65ec06548149"


async def test_a_malformed_model_list_is_reported_as_unavailable():
    status = await provider(responder({"models": "not-a-list"})).check_health()
    assert status.available is False


# --------------------------------------------------------------------------
# Plain generation
# --------------------------------------------------------------------------


async def test_plain_generation_returns_text_and_usage():
    response = await provider(responder(chat_body("안녕하세요"))).generate(request())

    assert response.text == "안녕하세요"
    assert response.provider == "ollama"
    assert response.model == MODEL
    assert response.finish_reason is FinishReason.STOP
    assert response.usage.input_tokens == 26
    assert response.usage.output_tokens == 42
    assert response.usage.total_tokens == 68
    assert response.duration_seconds > 0


async def test_the_request_is_non_streaming_and_carries_the_configured_model():
    captured: dict[str, object] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(http_request.content))
        assert http_request.url.path == "/api/chat"
        return httpx.Response(200, json=chat_body("ok"))

    await provider(handler).generate(request())

    assert captured["stream"] is False
    assert captured["model"] == MODEL
    assert captured["messages"] == [{"role": "user", "content": "질문"}]


async def test_options_are_mapped_to_ollama_names():
    captured: dict[str, object] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(http_request.content))
        return httpx.Response(200, json=chat_body("ok"))

    await provider(handler).generate(
        request(temperature=0.0, max_output_tokens=128, seed=7, stop=("END",))
    )

    assert captured["options"] == {
        "temperature": 0.0,
        "num_predict": 128,
        "seed": 7,
        "stop": ["END"],
    }


async def test_options_are_omitted_entirely_when_none_are_set():
    """Absent means "the server's default", which is not the same as a zero."""
    captured: dict[str, object] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(http_request.content))
        return httpx.Response(200, json=chat_body("ok"))

    await provider(handler).generate(request())

    assert "options" not in captured


async def test_a_system_message_is_sent_inline():
    captured: dict[str, object] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(http_request.content))
        return httpx.Response(200, json=chat_body("ok"))

    await provider(handler).generate(
        GenerationRequest(
            messages=(
                Message(role=MessageRole.SYSTEM, content="지시"),
                Message(role=MessageRole.USER, content="질문"),
            )
        )
    )

    assert captured["messages"][0] == {"role": "system", "content": "지시"}  # type: ignore[index]


async def test_length_finish_reason_produces_a_truncation_warning():
    body = chat_body("잘린 응답", done_reason="length")
    response = await provider(responder(body)).generate(request())

    assert response.finish_reason is FinishReason.LENGTH
    assert any("token limit" in warning for warning in response.warnings)


async def test_a_seed_with_a_nonzero_temperature_warns_rather_than_pretending():
    response = await provider(responder(chat_body("ok"))).generate(request(seed=1, temperature=0.8))

    assert any("temperature is 0" in warning for warning in response.warnings)


async def test_missing_usage_counts_stay_null():
    body = chat_body("ok")
    del body["prompt_eval_count"]
    del body["eval_count"]

    response = await provider(responder(body)).generate(request())

    assert response.usage.input_tokens is None
    assert response.usage.total_tokens is None


# --------------------------------------------------------------------------
# Structured generation
# --------------------------------------------------------------------------


async def test_structured_generation_sends_the_json_schema_as_format():
    captured: dict[str, object] = {}
    payload = '{"title": "제목", "keywords": ["센서"], "confidence": 0.9}'

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(http_request.content))
        return httpx.Response(200, json=chat_body(payload))

    generation = await provider(handler).generate_structured(request(), Summary)

    fmt = captured["format"]
    assert isinstance(fmt, dict)
    assert fmt["type"] == "object"
    # additionalProperties: false is what lets the server enforce the shape.
    assert fmt["additionalProperties"] is False
    assert generation.value.title == "제목"
    assert generation.response.structured_output_mode is (StructuredOutputMode.NATIVE_JSON_SCHEMA)


async def test_structured_output_is_validated_even_though_the_server_enforced_it():
    """An older server silently ignores `format`; trust, then verify."""
    body = chat_body("여기 답이 있습니다: 없음")

    with pytest.raises(LLMMalformedJSONError):
        await provider(responder(body)).generate_structured(request(), Summary)


async def test_structured_output_failing_the_schema_is_reported():
    body = chat_body('{"title": "제목"}')

    with pytest.raises(Exception) as exc_info:
        await provider(responder(body)).generate_structured(request(), Summary)

    assert exc_info.value.code.value == "llm_structured_output_validation_failed"  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# Error mapping
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "expected", "retryable"),
    [
        (404, {"error": "model 'x' not found"}, LLMModelNotFoundError, False),
        (401, {"error": "unauthorized"}, LLMAuthenticationError, False),
        (403, {"error": "forbidden"}, LLMAuthenticationError, False),
        (429, {"error": "too many requests"}, LLMRateLimitedError, True),
        (400, {"error": "invalid options"}, LLMInvalidRequestError, False),
        (
            400,
            {"error": "input exceeds context length"},
            LLMContextLengthExceededError,
            False,
        ),
        (503, {"error": "server loading"}, LLMProviderUnavailableError, True),
        (502, {"error": "bad gateway"}, LLMProviderUnavailableError, True),
        (500, {"error": "internal"}, LLMInternalProviderError, False),
    ],
)
async def test_http_status_mapping(
    status: int, body: dict[str, str], expected: type, retryable: bool
):
    with pytest.raises(expected) as exc_info:
        await provider(responder(body, status=status)).generate(request())

    assert exc_info.value.retryable is retryable  # type: ignore[attr-defined]
    assert exc_info.value.status == status  # type: ignore[attr-defined]


async def test_a_model_not_found_error_names_the_remedy():
    with pytest.raises(LLMModelNotFoundError) as exc_info:
        await provider(responder({"error": "not found"}, status=404)).generate(request())

    assert f"ollama pull {MODEL}" in exc_info.value.message


async def test_a_response_that_is_not_json_is_reported_as_invalid():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>proxy error</html>")

    with pytest.raises(LLMInvalidResponseError):
        await provider(handler).generate(request())


@pytest.mark.parametrize(
    "body",
    [
        {"done": True},
        {"message": "not-an-object"},
        {"message": {"role": "assistant"}},
        {"message": {"role": "assistant", "content": 42}},
    ],
)
async def test_unexpected_response_shapes_are_reported(body: dict[str, object]):
    with pytest.raises(LLMInvalidResponseError):
        await provider(responder(body)).generate(request())


async def test_a_read_timeout_maps_to_a_timeout_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    with pytest.raises(LLMTimeoutError):
        await provider(handler).generate(request())


# --------------------------------------------------------------------------
# Retry behaviour through the adapter
# --------------------------------------------------------------------------


async def test_a_transient_503_is_retried_and_the_attempt_count_is_reported():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "loading model"})
        return httpx.Response(200, json=chat_body("ok"))

    instance = provider(
        handler, retry_policy=RetryPolicy(max_attempts=3, initial_backoff_seconds=0.0)
    )

    response = await instance.generate(request())

    assert response.text == "ok"
    assert response.attempts == 2


async def test_a_400_is_not_retried():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": "invalid"})

    instance = provider(
        handler, retry_policy=RetryPolicy(max_attempts=3, initial_backoff_seconds=0.0)
    )

    with pytest.raises(LLMInvalidRequestError):
        await instance.generate(request())

    assert calls == 1


# --------------------------------------------------------------------------
# Privacy
# --------------------------------------------------------------------------


async def test_logs_carry_counts_but_never_prompt_or_response_text():
    secret_prompt = "기밀 특허 청구항 본문입니다"
    secret_reply = "기밀 생성 결과입니다"

    with capture_logs("claimtrace_api.llm.ollama") as records:
        await provider(responder(chat_body(secret_reply))).generate(request(secret_prompt))

    assert records
    rendered = " ".join(f"{record.getMessage()} {record.__dict__}" for record in records)
    assert secret_prompt not in rendered
    assert secret_reply not in rendered
    assert "prompt_characters" in rendered


async def test_an_error_message_never_quotes_the_provider_payload():
    """An Ollama error body can echo the prompt back."""
    leaked = "기밀 청구항"

    with pytest.raises(LLMInvalidRequestError) as exc_info:
        await provider(responder({"error": f"invalid input: {leaked}"}, status=400)).generate(
            request()
        )

    assert leaked not in exc_info.value.message
    assert leaked not in repr(exc_info.value)


async def test_metadata_reports_a_credentialled_url_safely():
    client = httpx.AsyncClient(transport=httpx.MockTransport(responder(tags_body(MODEL))))
    instance = OllamaProvider(
        base_url="http://user:secret@localhost:11434", model=MODEL, client=client
    )

    assert instance.get_metadata().base_url == "http://localhost:11434"


async def test_capabilities_do_not_claim_streaming():
    """The API supports it; this adapter does not implement it."""
    capabilities = provider(responder(chat_body("ok"))).get_metadata().capabilities

    assert capabilities.supports_streaming is False
    assert capabilities.structured_output_mode is StructuredOutputMode.NATIVE_JSON_SCHEMA
    assert capabilities.supports_usage_metadata is True
