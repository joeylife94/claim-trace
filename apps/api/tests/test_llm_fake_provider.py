"""The deterministic fake provider.

It satisfies the same protocol as the network adapters and runs the same JSON
pipeline, so these tests double as coverage of the paths above a provider - and
as proof that the whole application can run with no model and no network.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, Field

from claimtrace_api.llm.base import LLMProvider
from claimtrace_api.llm.errors import (
    LLMMalformedJSONError,
    LLMProviderUnavailableError,
    LLMStructuredValidationError,
    LLMUnsupportedCapabilityError,
)
from claimtrace_api.llm.fake import FakeLLMProvider
from claimtrace_api.llm.models import (
    FinishReason,
    GenerationOptions,
    GenerationRequest,
    Message,
    MessageRole,
    ProviderCapabilities,
    StructuredOutputMode,
)


class Summary(BaseModel):
    title: str
    keywords: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


def request(content: str = "질문", **options: object) -> GenerationRequest:
    return GenerationRequest(
        messages=(Message(role=MessageRole.USER, content=content),),
        options=GenerationOptions(**options),  # type: ignore[arg-type]
    )


def test_fake_provider_satisfies_the_protocol():
    assert isinstance(FakeLLMProvider(), LLMProvider)


async def test_plain_generation_returns_the_configured_text():
    provider = FakeLLMProvider(text="정해진 응답")
    response = await provider.generate(request())

    assert response.text == "정해진 응답"
    assert response.provider == "fake"
    assert response.finish_reason is FinishReason.STOP


async def test_generation_is_deterministic_across_instances():
    first = await FakeLLMProvider().generate(request("동일 입력"))
    second = await FakeLLMProvider().generate(request("동일 입력"))

    assert first.text == second.text
    assert first.usage == second.usage


async def test_scripted_responses_are_consumed_in_order_then_repeat():
    provider = FakeLLMProvider(text=["첫", "둘"])

    assert (await provider.generate(request())).text == "첫"
    assert (await provider.generate(request())).text == "둘"
    # Clamps rather than wrapping: a exhausted script keeps its last answer.
    assert (await provider.generate(request())).text == "둘"


async def test_usage_metadata_is_reported():
    response = await FakeLLMProvider().generate(request())

    assert response.usage.input_tokens is not None
    assert response.usage.output_tokens is not None
    assert response.usage.total_tokens == (
        response.usage.input_tokens + response.usage.output_tokens
    )


# --------------------------------------------------------------------------
# Structured output
# --------------------------------------------------------------------------


async def test_structured_generation_synthesises_a_conforming_payload():
    """No configuration needed: the fake answers any schema, so the whole app runs."""
    generation = await FakeLLMProvider().generate_structured(request(), Summary)

    assert isinstance(generation.value, Summary)
    assert generation.response.structured_output_mode is (StructuredOutputMode.NATIVE_JSON_SCHEMA)


async def test_configured_structured_text_is_returned_and_validated():
    provider = FakeLLMProvider(
        structured_text='{"title": "제목", "keywords": ["센서"], "confidence": 0.9}'
    )
    generation = await provider.generate_structured(request(), Summary)

    assert generation.value.title == "제목"
    assert generation.value.confidence == 0.9


async def test_invalid_json_flows_through_the_real_parser():
    provider = FakeLLMProvider(structured_text="이건 JSON이 아닙니다")

    with pytest.raises(LLMMalformedJSONError):
        await provider.generate_structured(request(), Summary)


async def test_schema_mismatch_flows_through_the_real_validator():
    provider = FakeLLMProvider(structured_text='{"title": "제목"}')

    with pytest.raises(LLMStructuredValidationError):
        await provider.generate_structured(request(), Summary)


async def test_structured_output_can_be_configured_unsupported():
    provider = FakeLLMProvider(
        capabilities=ProviderCapabilities(structured_output_mode=StructuredOutputMode.UNSUPPORTED)
    )
    with pytest.raises(LLMUnsupportedCapabilityError):
        await provider.generate_structured(request(), Summary)


# --------------------------------------------------------------------------
# Failure, timeout, cancellation
# --------------------------------------------------------------------------


async def test_configured_error_is_raised():
    error = LLMProviderUnavailableError("down", provider="fake")
    provider = FakeLLMProvider(fail_with=error)

    with pytest.raises(LLMProviderUnavailableError):
        await provider.generate(request())


async def test_a_transient_failure_can_be_scripted_to_recover():
    """Backs the retry tests: fail once, then succeed."""
    provider = FakeLLMProvider(
        fail_with=LLMProviderUnavailableError("busy"), fail_times=1, text="ok"
    )

    with pytest.raises(LLMProviderUnavailableError):
        await provider.generate(request())
    assert (await provider.generate(request())).text == "ok"


async def test_a_slow_provider_can_be_timed_out():
    provider = FakeLLMProvider(delay_seconds=5)

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await provider.generate(request())


async def test_cancellation_propagates_as_cancellation():
    """Never converted into a generic failure: the caller has gone away."""
    provider = FakeLLMProvider(delay_seconds=5)
    task = asyncio.create_task(provider.generate(request()))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_health_reports_a_configured_outage_without_raising():
    status = await FakeLLMProvider(healthy=False).check_health()

    assert status.available is False
    assert status.model_available is False
    assert status.error_code == "llm_provider_unavailable"


async def test_reachable_provider_can_still_be_missing_its_model():
    status = await FakeLLMProvider(model_available=False).check_health()

    assert status.available is True
    assert status.model_available is False


# --------------------------------------------------------------------------
# Call recording
# --------------------------------------------------------------------------


async def test_calls_are_recorded_in_order_with_their_requests():
    provider = FakeLLMProvider()
    await provider.check_health()
    await provider.generate(request("첫 질문"))
    await provider.generate_structured(request("둘째 질문"), Summary)

    kinds = [call.kind for call in provider.calls]
    assert kinds == ["check_health", "generate", "generate_structured"]

    assert provider.calls[1].request is not None
    assert provider.calls[1].request.messages[0].content == "첫 질문"
    assert provider.calls[2].output_model is Summary


async def test_recording_lets_a_test_assert_what_the_layer_above_sent():
    provider = FakeLLMProvider()
    await provider.generate(request("본문", temperature=0.0, max_output_tokens=64))

    sent = provider.calls[0].request
    assert sent is not None
    assert sent.options.temperature == 0.0
    assert sent.options.max_output_tokens == 64


async def test_metadata_is_deterministic_and_carries_no_url():
    metadata = FakeLLMProvider().get_metadata()

    assert metadata.provider == "fake"
    assert metadata.base_url is None
    assert metadata.transport == "in-process"


async def test_aclose_is_safe_to_call_repeatedly():
    provider = FakeLLMProvider()
    await provider.aclose()
    await provider.aclose()
