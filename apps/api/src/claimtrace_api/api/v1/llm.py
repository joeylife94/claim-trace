"""LLM provider diagnostics.

A narrow, development-facing surface with one purpose: proving that the
configured provider is reachable, that it generates text, and that it honours a
schema. It is not a chat API. There is no history, no streaming, no tool calling,
no model selection, and no retrieval - Phase 4A-1 builds the generation
infrastructure and nothing that uses it.

``GET /status`` is always served, because "the LLM is not configured" is exactly
the thing an operator needs the status endpoint to tell them. The two generation
endpoints are gated on ``LLM_DIAGNOSTICS_ENABLED``, which defaults to on in
development and off everywhere else.

``/health`` and ``/ready`` are untouched by any of this. The LLM is optional
infrastructure at this phase, and making the liveness of the whole service
depend on a model server would be a regression in operability, not a feature.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter

from claimtrace_api.api.deps import LLMServiceDep, SettingsDep
from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.llm.models import GenerationResponse, ProviderMetadata
from claimtrace_api.schemas.errors import ApiErrorResponse
from claimtrace_api.schemas.llm import (
    DiagnosticGenerateRequest,
    DiagnosticGenerateResponse,
    DiagnosticStructuredRequest,
    DiagnosticStructuredResponse,
    GenerationMetadataResponse,
    LLMStatusResponse,
    ProviderCapabilitiesResponse,
    SmokeTestSchema,
    TimeoutConfigResponse,
    TokenUsageResponse,
)

router = APIRouter(prefix="/llm", tags=["llm"])

#: Kept short and neutral. The model is being asked to demonstrate that it can
#: follow a schema, not to reason about anything.
#:
#: The confidence range is restated in prose because a JSON Schema ``maximum`` is
#: *not* enforced by constrained decoding. Ollama's grammar guarantees a number
#: in that position, not a number within bounds - during Phase 4A-1 validation
#: qwen2.5:1.5b returned ``"confidence": 3`` against a ``0.0-1.0`` schema, in
#: both Korean and English. Saying it in words is the only lever that reaches the
#: model; the bound is still enforced on arrival, and a model that ignores both
#: is reported rather than corrected.
_SMOKE_TEST_SYSTEM = (
    "You summarise short texts. Answer only with the requested JSON value. "
    "The confidence field must be a decimal between 0.0 and 1.0 inclusive, "
    "such as 0.8. Never use a percentage or a number greater than 1."
)


@router.get(
    "/status",
    response_model=LLMStatusResponse,
    summary="Local LLM provider status",
    description=(
        "Configuration and reachability of the local LLM provider.\n\n"
        "Always returns 200, including when the provider is unreachable: an "
        "unavailable model server is information this endpoint exists to report, "
        "not an error condition. Distinguish the four states through the "
        "`configured`, `available`, `model_available`, and `diagnostics_enabled` "
        "fields.\n\n"
        "Contains no credentials. The base URL is reported with any userinfo "
        "component removed."
    ),
)
async def llm_status(service: LLMServiceDep, settings: SettingsDep) -> LLMStatusResponse:
    metadata = service.get_metadata()
    health = await service.check_health()

    return LLMStatusResponse(
        provider=metadata.provider,
        model=metadata.model,
        model_version=metadata.model_version,
        base_url=metadata.base_url,
        transport=metadata.transport,
        # The provider object exists, so configuration resolved. A configuration
        # failure surfaces at startup instead, where it is a loud error rather
        # than a quiet false here.
        configured=True,
        available=health.available,
        model_available=health.model_available,
        detail=health.detail,
        error_code=health.error_code,
        health_check_duration_seconds=round(health.duration_seconds, 4),
        capabilities=_capabilities(metadata),
        timeouts=TimeoutConfigResponse(
            connect_seconds=settings.llm_connect_timeout_seconds,
            read_seconds=settings.llm_read_timeout_seconds,
            max_seconds=settings.llm_max_timeout_seconds,
        ),
        retry_max_attempts=settings.llm_retry_max_attempts,
        max_prompt_characters=settings.llm_max_prompt_characters,
        max_output_tokens=settings.llm_max_output_tokens,
        diagnostics_enabled=settings.llm_diagnostics_active,
    )


@router.post(
    "/diagnostics/generate",
    response_model=DiagnosticGenerateResponse,
    summary="Plain-text generation (development diagnostic)",
    description=(
        "Generates text with the configured provider and model.\n\n"
        "Development tooling: enabled by `LLM_DIAGNOSTICS_ENABLED`, which "
        "defaults to on in development and off in every other environment. "
        "Returns 404 when disabled.\n\n"
        "The model cannot be selected per request. Prompt length, output tokens, "
        "and timeout are bounded by configuration."
    ),
    responses={
        HTTPStatus.NOT_FOUND: {"model": ApiErrorResponse},
        HTTPStatus.BAD_REQUEST: {"model": ApiErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
        HTTPStatus.GATEWAY_TIMEOUT: {"model": ApiErrorResponse},
    },
)
async def diagnostic_generate(
    request: DiagnosticGenerateRequest,
    service: LLMServiceDep,
    settings: SettingsDep,
) -> DiagnosticGenerateResponse:
    _require_diagnostics(settings)

    response = await service.generate_text(
        prompt=request.prompt,
        system=request.system,
        temperature=request.temperature,
        max_output_tokens=request.max_output_tokens,
        timeout_seconds=request.timeout_seconds,
    )
    return DiagnosticGenerateResponse(text=response.text, metadata=_metadata(response))


@router.post(
    "/diagnostics/structured",
    response_model=DiagnosticStructuredResponse,
    summary="Schema-constrained generation (development diagnostic)",
    description=(
        "Generates JSON validated against one fixed, built-in smoke-test schema "
        "(`title`, `keywords`, `confidence`).\n\n"
        "The schema is not caller-supplied and cannot be: accepting an arbitrary "
        "JSON Schema over HTTP is out of scope for this phase. Internal Python "
        "callers pass any approved Pydantic model to the service directly.\n\n"
        "A 422 with `llm_structured_output_validation_failed` means the model "
        "produced JSON that does not satisfy the schema - which is a real result "
        "about the model, not a bug in the endpoint."
    ),
    responses={
        HTTPStatus.NOT_FOUND: {"model": ApiErrorResponse},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ApiErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
        HTTPStatus.NOT_IMPLEMENTED: {"model": ApiErrorResponse},
    },
)
async def diagnostic_structured(
    request: DiagnosticStructuredRequest,
    service: LLMServiceDep,
    settings: SettingsDep,
) -> DiagnosticStructuredResponse:
    _require_diagnostics(settings)

    generation = await service.generate_structured(
        prompt=request.prompt,
        output_model=SmokeTestSchema,
        system=_SMOKE_TEST_SYSTEM,
        temperature=request.temperature,
        max_output_tokens=request.max_output_tokens,
        timeout_seconds=request.timeout_seconds,
    )
    return DiagnosticStructuredResponse(
        result=generation.value, metadata=_metadata(generation.response)
    )


def _require_diagnostics(settings: Settings) -> None:
    """Refuse the generation endpoints when diagnostics are turned off.

    404 rather than 403: when disabled, this route is not part of the deployment's
    surface, and saying "forbidden" would confirm it exists.
    """
    if not settings.llm_diagnostics_active:
        raise AppError(
            ErrorCode.LLM_DIAGNOSTICS_DISABLED,
            "The LLM diagnostics endpoints are disabled for this deployment.",
        )


def _capabilities(metadata: ProviderMetadata) -> ProviderCapabilitiesResponse:
    capabilities = metadata.capabilities
    return ProviderCapabilitiesResponse(
        supports_text_generation=capabilities.supports_text_generation,
        supports_structured_output=capabilities.supports_structured_output,
        structured_output_mode=capabilities.structured_output_mode.value,
        structured_output_is_native=capabilities.structured_output_is_native,
        supports_seed=capabilities.supports_seed,
        supports_usage_metadata=capabilities.supports_usage_metadata,
        supports_model_listing=capabilities.supports_model_listing,
        supports_streaming=capabilities.supports_streaming,
    )


def _metadata(response: GenerationResponse) -> GenerationMetadataResponse:
    return GenerationMetadataResponse(
        provider=response.provider,
        model=response.model,
        model_version=response.model_version,
        finish_reason=response.finish_reason.value,
        usage=TokenUsageResponse(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
        ),
        duration_seconds=round(response.duration_seconds, 4),
        attempts=response.attempts,
        structured_output_mode=(
            response.structured_output_mode.value if response.structured_output_mode else None
        ),
        warnings=list(response.warnings),
    )
