"""The generation service and the provider registry.

Two things are being pinned here. The first is ordinary: bounds, error mapping,
cancellation. The second is architectural - that this service reaches nothing
else. Phase 4A-2 adds retrieval grounding, and the test that generation does not
touch the database today is what makes that an addition rather than an
untangling.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, Field, SecretStr

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import ERROR_STATUS, AppError, ErrorCode
from claimtrace_api.llm.errors import (
    LLMErrorCode,
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMStructuredValidationError,
)
from claimtrace_api.llm.fake import FakeLLMProvider
from claimtrace_api.llm.models import StructuredOutputMode
from claimtrace_api.llm.ollama import OllamaProvider
from claimtrace_api.llm.openai_compatible import OpenAICompatibleProvider
from claimtrace_api.llm.registry import build_llm_provider, build_retry_policy, build_timeouts
from claimtrace_api.services.llm_generation import LLMGenerationService


class Summary(BaseModel):
    title: str
    keywords: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "database_url": "postgresql+psycopg://unused:unused@localhost:5432/unused",
        "llm_provider": "fake",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def make_service(provider: FakeLLMProvider | None = None, **overrides: object):
    settings = make_settings(**overrides)
    return LLMGenerationService(provider=provider or FakeLLMProvider(), settings=settings)


# --------------------------------------------------------------------------
# Taxonomy consistency
# --------------------------------------------------------------------------


def test_every_llm_error_code_has_an_application_code_and_a_status():
    """The registry that keeps a new provider failure from reaching HTTP unmapped."""
    application_codes = {code.value for code in ErrorCode}

    for llm_code in LLMErrorCode:
        assert llm_code.value in application_codes, f"{llm_code.value} has no ErrorCode"
        assert ErrorCode(llm_code.value) in ERROR_STATUS


def test_llm_failures_are_not_all_collapsed_into_one_status():
    """A missing model, an oversized prompt, and a timeout are different problems."""
    assert ERROR_STATUS[ErrorCode.LLM_MODEL_NOT_FOUND] == 503
    assert ERROR_STATUS[ErrorCode.LLM_REQUEST_TIMEOUT] == 504
    assert ERROR_STATUS[ErrorCode.LLM_CONTEXT_LENGTH_EXCEEDED] == 422
    assert ERROR_STATUS[ErrorCode.LLM_INVALID_REQUEST] == 400
    assert ERROR_STATUS[ErrorCode.LLM_UNSUPPORTED_CAPABILITY] == 501


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


def test_the_configured_provider_is_built():
    assert isinstance(build_llm_provider(make_settings(llm_provider="fake")), FakeLLMProvider)


def test_the_ollama_provider_is_built_without_contacting_it():
    provider = build_llm_provider(
        make_settings(llm_provider="ollama", llm_ollama_base_url="http://localhost:11434")
    )
    assert isinstance(provider, OllamaProvider)
    assert provider.get_metadata().model_version is None


def test_the_openai_compatible_provider_is_built_with_its_configured_mode():
    provider = build_llm_provider(
        make_settings(
            llm_provider="openai_compatible",
            llm_openai_compatible_base_url="http://localhost:8000/v1",
            llm_structured_output_mode="prompt_constrained_json",
        )
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.get_metadata().capabilities.structured_output_mode is (
        StructuredOutputMode.PROMPT_CONSTRAINED_JSON
    )


def test_an_invalid_provider_name_is_rejected_by_configuration():
    with pytest.raises(ValueError, match="llm_provider"):
        make_settings(llm_provider="gpt-9")


def test_an_unusable_base_url_fails_fast_with_the_setting_named():
    from claimtrace_api.llm.errors import LLMConfigurationError

    with pytest.raises(LLMConfigurationError, match="LLM_OLLAMA_BASE_URL"):
        build_llm_provider(
            make_settings(llm_provider="ollama", llm_ollama_base_url="http://example.com")
        )


def test_an_empty_model_is_rejected():
    from claimtrace_api.llm.errors import LLMConfigurationError

    with pytest.raises(LLMConfigurationError, match="LLM_OLLAMA_MODEL"):
        build_llm_provider(make_settings(llm_provider="ollama", llm_ollama_model="  "))


def test_unselected_providers_are_never_constructed():
    """A fake-provider deployment must not need another provider's settings to be valid."""
    provider = build_llm_provider(
        make_settings(llm_provider="fake", llm_openai_compatible_base_url="not-a-url")
    )
    assert isinstance(provider, FakeLLMProvider)


def test_timeouts_and_retry_policy_come_from_settings():
    settings = make_settings(
        llm_connect_timeout_seconds=1.0,
        llm_read_timeout_seconds=30.0,
        llm_max_timeout_seconds=45.0,
        llm_retry_max_attempts=4,
    )

    assert build_timeouts(settings).overall_seconds == 45.0
    assert build_retry_policy(settings).max_attempts == 4


def test_the_api_key_is_held_as_a_secret():
    settings = make_settings(llm_openai_compatible_api_key="sk-local-secret")

    assert isinstance(settings.llm_openai_compatible_api_key, SecretStr)
    assert "sk-local-secret" not in repr(settings)
    assert "sk-local-secret" not in str(settings.model_dump())


# --------------------------------------------------------------------------
# Request construction and bounds
# --------------------------------------------------------------------------


async def test_plain_generation_reaches_the_provider():
    provider = FakeLLMProvider(text="응답")
    response = await make_service(provider).generate_text(prompt="질문")

    assert response.text == "응답"
    assert provider.calls[0].request is not None


async def test_a_system_message_is_placed_first():
    provider = FakeLLMProvider()
    await make_service(provider).generate_text(prompt="질문", system="지시")

    sent = provider.calls[0].request
    assert sent is not None
    assert [message.role.value for message in sent.messages] == ["system", "user"]


async def test_a_blank_system_message_is_dropped_rather_than_sent_empty():
    provider = FakeLLMProvider()
    await make_service(provider).generate_text(prompt="질문", system="   ")

    sent = provider.calls[0].request
    assert sent is not None
    assert len(sent.messages) == 1


async def test_an_empty_prompt_is_rejected():
    with pytest.raises(AppError) as exc_info:
        await make_service().generate_text(prompt="   ")

    assert exc_info.value.code is ErrorCode.LLM_INVALID_REQUEST


async def test_an_oversized_prompt_is_rejected_rather_than_truncated():
    """Truncating patent text would silently change the question being asked."""
    service = make_service(llm_max_prompt_characters=100)

    with pytest.raises(AppError) as exc_info:
        await service.generate_text(prompt="가" * 101)

    assert exc_info.value.code is ErrorCode.LLM_INVALID_REQUEST
    assert "limit is 100" in exc_info.value.message


async def test_the_system_message_counts_towards_the_prompt_limit():
    service = make_service(llm_max_prompt_characters=100)

    with pytest.raises(AppError):
        await service.generate_text(prompt="가" * 60, system="나" * 60)


async def test_an_excessive_output_token_request_is_clamped_not_rejected():
    provider = FakeLLMProvider()
    service = make_service(provider, llm_max_output_tokens=256)

    await service.generate_text(prompt="질문", max_output_tokens=9999)

    sent = provider.calls[0].request
    assert sent is not None
    assert sent.options.max_output_tokens == 256


async def test_an_excessive_timeout_is_clamped_to_the_configured_maximum():
    provider = FakeLLMProvider()
    service = make_service(provider, llm_max_timeout_seconds=30.0)

    await service.generate_text(prompt="질문", timeout_seconds=600)

    sent = provider.calls[0].request
    assert sent is not None
    assert sent.options.timeout_seconds == 30.0


async def test_a_lower_request_timeout_is_honoured():
    provider = FakeLLMProvider()
    service = make_service(provider, llm_max_timeout_seconds=30.0)

    await service.generate_text(prompt="질문", timeout_seconds=5)

    sent = provider.calls[0].request
    assert sent is not None
    assert sent.options.timeout_seconds == 5


async def test_an_out_of_range_temperature_is_rejected():
    with pytest.raises(AppError) as exc_info:
        await make_service().generate_text(prompt="질문", temperature=5.0)

    assert exc_info.value.code is ErrorCode.LLM_INVALID_REQUEST


async def test_every_request_gets_a_correlation_id_unrelated_to_its_content():
    provider = FakeLLMProvider()
    service = make_service(provider)

    await service.generate_text(prompt="동일한 기밀 본문")
    await service.generate_text(prompt="동일한 기밀 본문")

    first, second = provider.calls[0].request, provider.calls[1].request
    assert first is not None and second is not None
    # Distinct for identical input: an id derived from the prompt would be a
    # weak fingerprint of confidential text in every log line.
    assert first.request_id != second.request_id


# --------------------------------------------------------------------------
# Structured generation
# --------------------------------------------------------------------------


async def test_structured_generation_returns_a_validated_model():
    generation = await make_service().generate_structured(prompt="요약해줘", output_model=Summary)

    assert isinstance(generation.value, Summary)
    assert generation.response.structured_output_mode is not None


async def test_a_schema_violation_maps_to_the_validation_error_code():
    provider = FakeLLMProvider(structured_text='{"title": "제목"}')

    with pytest.raises(AppError) as exc_info:
        await make_service(provider).generate_structured(prompt="요약", output_model=Summary)

    assert exc_info.value.code is ErrorCode.LLM_STRUCTURED_OUTPUT_VALIDATION_FAILED


async def test_malformed_json_maps_to_the_malformed_json_code():
    provider = FakeLLMProvider(structured_text="JSON 아님")

    with pytest.raises(AppError) as exc_info:
        await make_service(provider).generate_structured(prompt="요약", output_model=Summary)

    assert exc_info.value.code is ErrorCode.LLM_MALFORMED_JSON


# --------------------------------------------------------------------------
# Error mapping, timeouts, cancellation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LLMProviderUnavailableError("down"), ErrorCode.LLM_PROVIDER_UNAVAILABLE),
        (LLMModelNotFoundError("missing"), ErrorCode.LLM_MODEL_NOT_FOUND),
        (LLMStructuredValidationError("bad"), ErrorCode.LLM_STRUCTURED_OUTPUT_VALIDATION_FAILED),
    ],
)
async def test_provider_errors_map_to_application_codes(error: Exception, expected: ErrorCode):
    provider = FakeLLMProvider(fail_with=error)  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc_info:
        await make_service(provider).generate_text(prompt="질문")

    assert exc_info.value.code is expected


async def test_the_mapped_message_stays_client_safe():
    provider = FakeLLMProvider(fail_with=LLMModelNotFoundError("model qwen2.5 is not installed"))

    with pytest.raises(AppError) as exc_info:
        await make_service(provider).generate_text(prompt="기밀 본문")

    assert "기밀" not in exc_info.value.message


async def test_cancellation_propagates_rather_than_becoming_an_internal_error():
    provider = FakeLLMProvider(delay_seconds=5)
    service = make_service(provider)
    task = asyncio.create_task(service.generate_text(prompt="질문"))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_health_check_failure_becomes_a_status_not_an_exception():
    status = await make_service(FakeLLMProvider(healthy=False)).check_health()

    assert status.available is False


# --------------------------------------------------------------------------
# Architectural boundary
# --------------------------------------------------------------------------


def test_the_service_takes_no_session_and_no_retrieval_collaborator():
    """Phase 4A-1 generates; it does not ground. Asserted, not just intended."""
    import inspect

    parameters = set(inspect.signature(LLMGenerationService.__init__).parameters)
    assert parameters == {"self", "provider", "settings"}


def test_the_llm_package_imports_no_web_or_database_framework():
    """The boundary is only a boundary if it cannot reach past itself."""
    import pkgutil

    import claimtrace_api.llm as llm_package

    forbidden = ("fastapi", "sqlalchemy", "starlette", "psycopg", "alembic")
    sources: list[str] = []

    for module in pkgutil.iter_modules(llm_package.__path__):
        path = f"{llm_package.__path__[0]}/{module.name}.py"
        with open(path, encoding="utf-8") as handle:
            sources.append(handle.read())

    joined = "\n".join(sources)
    for name in forbidden:
        assert f"import {name}" not in joined, f"llm package imports {name}"
        assert f"from {name}" not in joined, f"llm package imports from {name}"
