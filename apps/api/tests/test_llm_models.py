"""Provider-neutral request and response types.

These are the invariants every adapter is allowed to assume. If a malformed
message list can reach an adapter, each one rejects it differently and the
"boundary" has stopped being one - so the rejections are tested here rather than
per provider.
"""

from __future__ import annotations

import pytest

from claimtrace_api.llm.errors import LLMInvalidRequestError
from claimtrace_api.llm.models import (
    MAX_OUTPUT_TOKENS_LIMIT,
    MAX_STOP_SEQUENCES,
    MAX_TEMPERATURE,
    MAX_TIMEOUT_SECONDS,
    FinishReason,
    GenerationOptions,
    GenerationRequest,
    GenerationResponse,
    HealthStatus,
    Message,
    MessageRole,
    ProviderCapabilities,
    ProviderMetadata,
    StructuredOutputMode,
    TokenUsage,
    safe_base_url,
)


def user(content: str = "질문") -> Message:
    return Message(role=MessageRole.USER, content=content)


def system(content: str = "You are helpful.") -> Message:
    return Message(role=MessageRole.SYSTEM, content=content)


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------


def test_message_rejects_blank_content():
    with pytest.raises(LLMInvalidRequestError):
        Message(role=MessageRole.USER, content="   \n ")


def test_supported_roles_are_exactly_three():
    """Tool and function roles are absent because no adapter implements them."""
    assert {role.value for role in MessageRole} == {"system", "user", "assistant"}


# --------------------------------------------------------------------------
# Request validation
# --------------------------------------------------------------------------


def test_empty_message_sequence_is_rejected():
    with pytest.raises(LLMInvalidRequestError, match="At least one message"):
        GenerationRequest(messages=())


def test_valid_ordering_is_accepted():
    request = GenerationRequest(
        messages=(
            system(),
            user("첫 질문"),
            Message(role=MessageRole.ASSISTANT, content="답변"),
            user("두 번째 질문"),
        )
    )
    assert len(request.messages) == 4
    assert request.system_message is not None
    assert len(request.conversation) == 3


def test_system_message_must_be_first():
    with pytest.raises(LLMInvalidRequestError, match="must be the first message"):
        GenerationRequest(messages=(user(), system(), user()))


def test_at_most_one_system_message():
    with pytest.raises(LLMInvalidRequestError, match="At most one system message"):
        GenerationRequest(messages=(system(), system(), user()))


def test_last_message_must_be_from_the_user():
    with pytest.raises(LLMInvalidRequestError, match="last message must be a user"):
        GenerationRequest(messages=(user(), Message(role=MessageRole.ASSISTANT, content="답변")))


def test_conversation_excludes_a_leading_system_turn():
    request = GenerationRequest(messages=(system(), user("본문")))
    assert request.conversation == (user("본문"),)


def test_request_carries_no_model_field():
    """A caller may not choose the model; configuration does.

    Asserted structurally rather than by comment: this is the property that keeps
    a diagnostics request from repointing the deployment at another model.
    """
    assert not hasattr(GenerationRequest(messages=(user(),)), "model")


# --------------------------------------------------------------------------
# Option bounds
# --------------------------------------------------------------------------


@pytest.mark.parametrize("temperature", [-0.1, MAX_TEMPERATURE + 0.1])
def test_temperature_bounds(temperature: float):
    with pytest.raises(LLMInvalidRequestError, match="temperature"):
        GenerationOptions(temperature=temperature)


@pytest.mark.parametrize("temperature", [0.0, 1.0, MAX_TEMPERATURE])
def test_temperature_accepts_the_documented_range(temperature: float):
    assert GenerationOptions(temperature=temperature).temperature == temperature


@pytest.mark.parametrize("tokens", [0, -1, MAX_OUTPUT_TOKENS_LIMIT + 1])
def test_output_token_bounds(tokens: int):
    with pytest.raises(LLMInvalidRequestError, match="max_output_tokens"):
        GenerationOptions(max_output_tokens=tokens)


@pytest.mark.parametrize("timeout", [0, -1, MAX_TIMEOUT_SECONDS + 1])
def test_timeout_bounds(timeout: float):
    with pytest.raises(LLMInvalidRequestError, match="timeout_seconds"):
        GenerationOptions(timeout_seconds=timeout)


def test_stop_sequence_count_is_bounded():
    with pytest.raises(LLMInvalidRequestError, match="stop sequences"):
        GenerationOptions(stop=tuple(str(i) for i in range(MAX_STOP_SEQUENCES + 1)))


def test_empty_stop_sequence_is_rejected():
    with pytest.raises(LLMInvalidRequestError, match="may not be empty"):
        GenerationOptions(stop=("ok", ""))


def test_temperature_none_is_distinct_from_zero():
    """None means the server default; 0.0 means greedy decoding."""
    assert GenerationOptions().temperature is None
    assert GenerationOptions(temperature=0.0).temperature == 0.0


# --------------------------------------------------------------------------
# Usage metadata
# --------------------------------------------------------------------------


def test_total_is_derived_when_both_parts_are_known():
    usage = TokenUsage.create(input_tokens=10, output_tokens=5)
    assert usage.total_tokens == 15


def test_total_is_not_invented_from_one_part():
    """A missing count stays missing rather than becoming a fabricated number."""
    usage = TokenUsage.create(input_tokens=10)
    assert usage.total_tokens is None
    assert usage.output_tokens is None


def test_provider_supplied_total_is_preserved():
    usage = TokenUsage.create(input_tokens=10, output_tokens=5, total_tokens=99)
    assert usage.total_tokens == 99


def test_unavailable_usage_reports_empty_rather_than_zero():
    assert TokenUsage().is_empty is True
    assert TokenUsage(input_tokens=0).is_empty is False


# --------------------------------------------------------------------------
# Safe logging and serialization
# --------------------------------------------------------------------------


def test_request_log_fields_contain_no_message_content():
    request = GenerationRequest(
        messages=(system("기밀 시스템 지시"), user("기밀 특허 청구항 본문")),
        request_id="abc123",
    )
    serialized = repr(request.log_fields())

    assert "기밀" not in serialized
    assert request.log_fields()["prompt_characters"] == request.prompt_characters
    assert request.log_fields()["message_count"] == 2
    assert request.log_fields()["has_system_message"] is True


def test_response_log_fields_contain_no_generated_text():
    response = GenerationResponse(
        text="생성된 기밀 응답", provider="fake", model="m", duration_seconds=1.2345678
    )
    fields = response.log_fields()

    assert "생성된" not in repr(fields)
    assert fields["response_characters"] == len("생성된 기밀 응답")
    assert fields["duration_seconds"] == 1.2346


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://user:secret@host:11434", "http://host:11434"),
        ("https://token@vllm.internal/v1", "https://vllm.internal/v1"),
        ("http://localhost:11434", "http://localhost:11434"),
        (None, None),
        ("", ""),
    ],
)
def test_safe_base_url_strips_credentials(url: str | None, expected: str | None):
    result = safe_base_url(url)
    assert result == expected
    if result:
        assert "secret" not in result
        assert "token" not in result


def test_provider_metadata_is_serializable_without_secrets():
    metadata = ProviderMetadata(
        provider="ollama",
        model="qwen2.5:1.5b",
        base_url=safe_base_url("http://user:pw@host:11434"),
        capabilities=ProviderCapabilities(),
    )
    assert "pw" not in repr(metadata)
    assert metadata.base_url == "http://host:11434"


# --------------------------------------------------------------------------
# Capabilities
# --------------------------------------------------------------------------


def test_capabilities_default_to_unsupported():
    """A capability is opt-in: nothing is claimed until an adapter declares it."""
    capabilities = ProviderCapabilities()

    assert capabilities.structured_output_mode is StructuredOutputMode.UNSUPPORTED
    assert capabilities.supports_structured_output is False
    assert capabilities.supports_seed is False
    assert capabilities.supports_usage_metadata is False
    assert capabilities.supports_model_listing is False
    assert capabilities.supports_streaming is False


@pytest.mark.parametrize(
    ("mode", "native"),
    [
        (StructuredOutputMode.NATIVE_JSON_SCHEMA, True),
        (StructuredOutputMode.NATIVE_JSON_OBJECT, True),
        (StructuredOutputMode.PROMPT_CONSTRAINED_JSON, False),
        (StructuredOutputMode.UNSUPPORTED, False),
    ],
)
def test_native_enforcement_is_distinct_from_being_supported(
    mode: StructuredOutputMode, native: bool
):
    """A prompt-only fallback supports structured output but does not enforce it."""
    capabilities = ProviderCapabilities(structured_output_mode=mode)
    assert capabilities.structured_output_is_native is native


def test_streaming_is_reported_unsupported_everywhere_in_this_phase():
    assert ProviderCapabilities(supports_streaming=False).supports_streaming is False


# --------------------------------------------------------------------------
# Response helpers
# --------------------------------------------------------------------------


def test_warnings_are_appended_in_order_without_duplicates():
    response = GenerationResponse(text="t", provider="p", model="m")
    warned = response.with_warning("first").with_warning("second").with_warning("first")

    assert warned.warnings == ("first", "second")
    # The original is untouched: the response is frozen.
    assert response.warnings == ()


def test_health_status_separates_reachability_from_model_availability():
    status = HealthStatus(available=True, model_available=False, detail="no model")
    assert status.available is True
    assert status.model_available is False


def test_finish_reason_has_an_explicit_unknown():
    assert FinishReason.UNKNOWN.value == "unknown"
