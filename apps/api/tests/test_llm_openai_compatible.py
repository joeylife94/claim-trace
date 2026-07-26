"""OpenAI-compatible adapter contract tests.

Run against ``httpx.MockTransport`` reproducing the chat-completions wire format
a local vLLM server speaks. No GPU, no server, and no model are involved: these
pin the request and response contract, and the live-vLLM status is recorded in
``docs/ARCHITECTURE.md``.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import BaseModel, Field, SecretStr

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
    LLMUnsupportedCapabilityError,
)
from claimtrace_api.llm.models import (
    FinishReason,
    GenerationOptions,
    GenerationRequest,
    Message,
    MessageRole,
    StructuredOutputMode,
)
from claimtrace_api.llm.openai_compatible import OpenAICompatibleProvider
from claimtrace_api.llm.retry import RetryPolicy
from tests.conftest import capture_logs

BASE_URL = "http://vllm:8000/v1"
MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

Handler = Callable[[httpx.Request], httpx.Response]


class Summary(BaseModel):
    title: str
    keywords: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


def completion_body(content: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": "chatcmpl-abc123",
        "object": "chat.completion",
        "created": 1_760_000_000,
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 31, "completion_tokens": 57, "total_tokens": 88},
    }
    body.update(overrides)
    return body


def models_body(*ids: str) -> dict[str, object]:
    return {
        "object": "list",
        "data": [{"id": model_id, "object": "model"} for model_id in ids],
    }


def provider(
    handler: Handler,
    *,
    mode: StructuredOutputMode = StructuredOutputMode.NATIVE_JSON_SCHEMA,
    api_key: SecretStr | None = None,
    retry_policy: RetryPolicy | None = None,
) -> OpenAICompatibleProvider:
    client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        base_url=BASE_URL,
        model=MODEL,
        api_key=api_key,
        structured_output_mode=mode,
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
# Model listing and health
# --------------------------------------------------------------------------


async def test_model_listing_confirms_the_configured_model_is_served():
    status = await provider(responder(models_body(MODEL))).check_health()

    assert status.available is True
    assert status.model_available is True


async def test_a_server_serving_a_different_model_is_reachable_but_unusable():
    status = await provider(responder(models_body("some/other-model"))).check_health()

    assert status.available is True
    assert status.model_available is False
    assert status.error_code == "llm_model_not_found"


async def test_health_reports_an_unreachable_server_without_raising():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    status = await provider(handler).check_health()

    assert status.available is False
    assert status.error_code == "llm_connection_error"


async def test_the_models_endpoint_is_requested_under_the_configured_prefix():
    seen: list[str] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        seen.append(http_request.url.path)
        return httpx.Response(200, json=models_body(MODEL))

    await provider(handler).check_health()

    assert seen == ["/v1/models"]


# --------------------------------------------------------------------------
# Plain generation
# --------------------------------------------------------------------------


async def test_plain_chat_completion_returns_text_usage_and_request_id():
    response = await provider(responder(completion_body("안녕하세요"))).generate(request())

    assert response.text == "안녕하세요"
    assert response.provider == "openai_compatible"
    assert response.finish_reason is FinishReason.STOP
    assert response.usage.input_tokens == 31
    assert response.usage.output_tokens == 57
    assert response.usage.total_tokens == 88
    assert response.provider_request_id == "chatcmpl-abc123"


async def test_the_request_targets_chat_completions_and_is_non_streaming():
    captured: dict[str, object] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.url.path == "/v1/chat/completions"
        captured.update(json.loads(http_request.content))
        return httpx.Response(200, json=completion_body("ok"))

    await provider(handler).generate(request())

    assert captured["stream"] is False
    assert captured["model"] == MODEL


async def test_options_use_openai_field_names():
    captured: dict[str, object] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(http_request.content))
        return httpx.Response(200, json=completion_body("ok"))

    await provider(handler).generate(
        request(temperature=0.2, max_output_tokens=256, seed=11, stop=("###",))
    )

    assert captured["temperature"] == 0.2
    assert captured["max_tokens"] == 256
    assert captured["seed"] == 11
    assert captured["stop"] == ["###"]


async def test_a_provider_supplied_total_is_preserved_over_the_derived_one():
    body = completion_body(
        "ok", usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 999}
    )
    response = await provider(responder(body)).generate(request())

    assert response.usage.total_tokens == 999


async def test_absent_usage_stays_null_rather_than_zero():
    body = completion_body("ok")
    del body["usage"]

    response = await provider(responder(body)).generate(request())

    assert response.usage.input_tokens is None
    assert response.usage.output_tokens is None
    assert response.usage.is_empty is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("stop", FinishReason.STOP),
        ("length", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
        ("something_new", FinishReason.UNKNOWN),
        (None, FinishReason.UNKNOWN),
    ],
)
async def test_finish_reason_mapping(raw: str | None, expected: FinishReason):
    body = completion_body("ok")
    body["choices"] = [
        {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": raw}
    ]

    response = await provider(responder(body)).generate(request())
    assert response.finish_reason is expected


# --------------------------------------------------------------------------
# Structured output modes
# --------------------------------------------------------------------------


async def test_native_json_schema_mode_sends_a_strict_response_format():
    captured: dict[str, object] = {}
    payload = '{"title": "제목", "keywords": ["센서"], "confidence": 0.7}'

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(http_request.content))
        return httpx.Response(200, json=completion_body(payload))

    generation = await provider(handler).generate_structured(request(), Summary)

    response_format = captured["response_format"]
    assert isinstance(response_format, dict)
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True  # type: ignore[index]
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False  # type: ignore[index]
    assert generation.value.title == "제목"
    # Server-enforced: no degradation warning.
    assert generation.response.warnings == ()


async def test_json_object_mode_falls_back_and_says_so():
    payload = '{"title": "제목", "keywords": ["센서"], "confidence": 0.7}'
    captured: dict[str, object] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(http_request.content))
        return httpx.Response(200, json=completion_body(payload))

    generation = await provider(
        handler, mode=StructuredOutputMode.NATIVE_JSON_OBJECT
    ).generate_structured(request(), Summary)

    assert captured["response_format"] == {"type": "json_object"}
    assert generation.value.title == "제목"
    # Valid JSON was guaranteed; the *schema* was not.
    assert any("did not enforce the schema" in w for w in generation.response.warnings)


async def test_prompt_constrained_mode_sends_no_response_format_and_warns():
    """Sending response_format to a server that ignores it is how an unenforced
    request comes back looking enforced."""
    payload = '{"title": "제목", "keywords": ["센서"], "confidence": 0.7}'
    captured: dict[str, object] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(http_request.content))
        return httpx.Response(200, json=completion_body(payload))

    generation = await provider(
        handler, mode=StructuredOutputMode.PROMPT_CONSTRAINED_JSON
    ).generate_structured(request(), Summary)

    assert "response_format" not in captured
    # The schema is carried in the conversation instead.
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert "JSON Schema" in messages[-1]["content"]
    assert any("rather than enforced" in w for w in generation.response.warnings)


async def test_prompt_constrained_mode_still_validates_strictly():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion_body("죄송합니다, 답변할 수 없습니다."))

    with pytest.raises(LLMMalformedJSONError):
        await provider(
            handler, mode=StructuredOutputMode.PROMPT_CONSTRAINED_JSON
        ).generate_structured(request(), Summary)


async def test_unsupported_mode_refuses_rather_than_guessing():
    with pytest.raises(LLMUnsupportedCapabilityError):
        await provider(
            responder(completion_body("{}")), mode=StructuredOutputMode.UNSUPPORTED
        ).generate_structured(request(), Summary)


async def test_capabilities_report_the_configured_mode():
    instance = provider(
        responder(completion_body("ok")), mode=StructuredOutputMode.PROMPT_CONSTRAINED_JSON
    )
    capabilities = instance.get_metadata().capabilities

    assert capabilities.structured_output_mode is StructuredOutputMode.PROMPT_CONSTRAINED_JSON
    # Supported, but explicitly not native: the distinction the caller needs.
    assert capabilities.supports_structured_output is True
    assert capabilities.structured_output_is_native is False
    assert capabilities.supports_streaming is False


# --------------------------------------------------------------------------
# Error mapping
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "expected", "retryable"),
    [
        (401, {"error": {"message": "invalid api key"}}, LLMAuthenticationError, False),
        (403, {"error": {"message": "forbidden"}}, LLMAuthenticationError, False),
        (429, {"error": {"message": "rate limit"}}, LLMRateLimitedError, True),
        (
            404,
            {"error": {"message": "model does not exist", "code": "model_not_found"}},
            LLMModelNotFoundError,
            False,
        ),
        (
            400,
            {"error": {"message": "maximum context length is 4096", "code": "x"}},
            LLMContextLengthExceededError,
            False,
        ),
        (400, {"error": {"message": "bad parameter"}}, LLMInvalidRequestError, False),
        (422, {"error": {"message": "unprocessable"}}, LLMInvalidRequestError, False),
        (503, {"error": {"message": "server overloaded"}}, LLMProviderUnavailableError, True),
        (500, {"error": {"message": "internal"}}, LLMInternalProviderError, False),
    ],
)
async def test_http_status_mapping(
    status: int, body: dict[str, object], expected: type, retryable: bool
):
    with pytest.raises(expected) as exc_info:
        await provider(responder(body, status=status)).generate(request())

    assert exc_info.value.retryable is retryable  # type: ignore[attr-defined]
    assert exc_info.value.status == status  # type: ignore[attr-defined]


async def test_a_context_length_error_is_recognised_from_the_error_code():
    body = {"error": {"message": "too long", "code": "context_length_exceeded"}}

    with pytest.raises(LLMContextLengthExceededError):
        await provider(responder(body, status=400)).generate(request())


async def test_a_response_that_is_not_json_is_reported_as_invalid():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="upstream connect error")

    with pytest.raises(LLMInvalidResponseError):
        await provider(handler).generate(request())


@pytest.mark.parametrize(
    "body",
    [
        {"id": "x"},
        {"choices": []},
        {"choices": "not-a-list"},
        {"choices": [{"index": 0}]},
        {"choices": [{"index": 0, "message": {"role": "assistant"}}]},
        {"choices": [{"index": 0, "message": {"role": "assistant", "content": None}}]},
    ],
)
async def test_unexpected_response_shapes_are_reported(body: dict[str, object]):
    with pytest.raises(LLMInvalidResponseError):
        await provider(responder(body)).generate(request())


async def test_a_read_timeout_maps_to_a_timeout_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(LLMTimeoutError):
        await provider(handler).generate(request())


# --------------------------------------------------------------------------
# Retry
# --------------------------------------------------------------------------


async def test_a_transient_503_is_retried():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        return httpx.Response(200, json=completion_body("ok"))

    response = await provider(
        handler, retry_policy=RetryPolicy(max_attempts=3, initial_backoff_seconds=0.0)
    ).generate(request())

    assert response.text == "ok"
    assert response.attempts == 2


async def test_an_authentication_failure_is_not_retried():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    with pytest.raises(LLMAuthenticationError):
        await provider(
            handler, retry_policy=RetryPolicy(max_attempts=3, initial_backoff_seconds=0.0)
        ).generate(request())

    assert calls == 1


# --------------------------------------------------------------------------
# API key handling
# --------------------------------------------------------------------------


async def test_the_api_key_is_sent_as_a_bearer_token():
    seen: dict[str, str] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        seen["auth"] = http_request.headers.get("authorization", "")
        return httpx.Response(200, json=completion_body("ok"))

    await provider(handler, api_key=SecretStr("sk-local-secret")).generate(request())

    assert seen["auth"] == "Bearer sk-local-secret"


async def test_no_authorization_header_is_sent_when_no_key_is_configured():
    seen: dict[str, str | None] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        seen["auth"] = http_request.headers.get("authorization")
        return httpx.Response(200, json=completion_body("ok"))

    await provider(handler).generate(request())

    assert seen["auth"] is None


async def test_the_api_key_never_appears_in_repr_or_metadata():
    instance = provider(responder(completion_body("ok")), api_key=SecretStr("sk-local-secret"))

    assert "sk-local-secret" not in repr(instance)
    assert "sk-local-secret" not in repr(instance.get_metadata())
    assert "sk-local-secret" not in repr(vars(instance))


async def test_the_api_key_never_reaches_an_error_or_a_log():
    key = "sk-local-secret"

    with (
        capture_logs("claimtrace_api.llm.openai_compatible") as records,
        pytest.raises(LLMAuthenticationError) as exc_info,
    ):
        await provider(
            responder({"error": {"message": "invalid api key"}}, status=401),
            api_key=SecretStr(key),
        ).generate(request())

    assert key not in exc_info.value.message
    assert key not in repr(exc_info.value)
    assert key not in " ".join(f"{r.getMessage()} {r.__dict__}" for r in records)


# --------------------------------------------------------------------------
# Privacy
# --------------------------------------------------------------------------


async def test_logs_carry_counts_but_never_prompt_or_response_text():
    secret_prompt = "기밀 특허 청구항 본문"
    secret_reply = "기밀 생성 결과"

    with capture_logs("claimtrace_api.llm.openai_compatible") as records:
        await provider(responder(completion_body(secret_reply))).generate(request(secret_prompt))

    rendered = " ".join(f"{r.getMessage()} {r.__dict__}" for r in records)
    assert secret_prompt not in rendered
    assert secret_reply not in rendered
    assert "prompt_characters" in rendered


async def test_an_error_message_never_quotes_the_provider_payload():
    """An OpenAI-style error routinely echoes the offending request back."""
    leaked = "기밀 청구항 본문"

    with pytest.raises(LLMInvalidRequestError) as exc_info:
        await provider(
            responder({"error": {"message": f"invalid input: {leaked}"}}, status=400)
        ).generate(request())

    assert leaked not in exc_info.value.message


async def test_metadata_reports_a_credentialled_url_safely():
    client = httpx.AsyncClient(transport=httpx.MockTransport(responder(models_body(MODEL))))
    instance = OpenAICompatibleProvider(
        base_url="http://user:secret@localhost:8000/v1", model=MODEL, client=client
    )

    assert instance.get_metadata().base_url == "http://localhost:8000/v1"
