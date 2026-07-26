"""Request and response models for the LLM diagnostics endpoints.

Two rules shape everything here.

*No secrets leave.* The status response carries a base URL that has already been
stripped of userinfo, and there is no field anywhere in this module that an API
key could reach - not even an optional one.

*Nothing about the provider is caller-controlled.* There is no model field, no
provider field, no base URL field, and no JSON Schema field on any request. A
diagnostics endpoint that accepted any of those would let a request repoint the
deployment at another server or spend its budget on a larger model, which is a
much bigger surface than "prove the provider works" needs.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Ceilings enforced by the schema itself, independent of configuration.
#: Settings may lower them further; see the route handlers.
PROMPT_MAX_LENGTH = 8000
SYSTEM_MAX_LENGTH = 2000

#: A prompt, bounded and required to contain something other than whitespace.
#: Blankness is rejected here rather than in the service so that "" and "   "
#: produce the same 422 - two spellings of the same mistake should not return
#: two different statuses.
Prompt = Annotated[str, Field(min_length=1, max_length=PROMPT_MAX_LENGTH)]


def _reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class ProviderCapabilitiesResponse(BaseModel):
    """What the configured provider has been validated to do."""

    supports_text_generation: bool
    supports_structured_output: bool
    structured_output_mode: str
    structured_output_is_native: bool
    supports_seed: bool
    supports_usage_metadata: bool
    supports_model_listing: bool
    supports_streaming: bool


class TimeoutConfigResponse(BaseModel):
    """The deadlines a generation is bounded by, in seconds."""

    connect_seconds: float
    read_seconds: float
    max_seconds: float


class LLMStatusResponse(BaseModel):
    """Configuration and reachability of the local LLM provider.

    The four states an operator needs to tell apart are separate fields rather
    than one enum: ``configured`` (the application built a provider),
    ``available`` (the server answered), ``model_available`` (the configured tag
    is actually there), and ``diagnostics_enabled``. A single status string would
    collapse "Ollama is not running" and "Ollama is running without the model",
    which have completely different fixes.
    """

    provider: str
    model: str
    model_version: str | None
    #: Userinfo already stripped. Null for the fake provider, which has no URL.
    base_url: str | None
    transport: str
    configured: bool
    available: bool
    model_available: bool
    #: Operator-facing summary of the last check. Never a provider payload.
    detail: str
    error_code: str | None
    health_check_duration_seconds: float
    capabilities: ProviderCapabilitiesResponse
    timeouts: TimeoutConfigResponse
    retry_max_attempts: int
    max_prompt_characters: int
    max_output_tokens: int
    diagnostics_enabled: bool


class TokenUsageResponse(BaseModel):
    """Token counts, each null when the provider did not report it.

    Nullable rather than zero-filled: "not reported" and "zero tokens" are
    different facts, and a UI that renders a fabricated 0 as a measurement is
    worse than one that renders a dash.
    """

    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class GenerationMetadataResponse(BaseModel):
    """How an answer was produced - everything except the answer itself."""

    provider: str
    model: str
    model_version: str | None
    finish_reason: str
    usage: TokenUsageResponse
    duration_seconds: float
    attempts: int
    structured_output_mode: str | None
    #: Degraded capabilities, surfaced rather than swallowed: a prompt-only JSON
    #: fallback produces a correct-looking answer that was never enforced, and
    #: the caller has to be able to see that.
    warnings: list[str]


class DiagnosticGenerateRequest(BaseModel):
    """One bounded plain-text generation.

    Note the absence of a model field: the model comes from server configuration
    and cannot be overridden per request.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: Prompt
    system: str | None = Field(default=None, max_length=SYSTEM_MAX_LENGTH)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1, le=4096)
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)

    _prompt_not_blank = field_validator("prompt")(lambda value: _reject_blank(value))


class DiagnosticGenerateResponse(BaseModel):
    """The generated text plus its metadata."""

    text: str
    metadata: GenerationMetadataResponse


# The built-in structured-output smoke test.
#
# Deliberately trivial and deliberately non-legal. Its only job is to prove that
# schema-constrained decoding works end to end - that the provider was asked for
# a shape and returned that shape. Reading anything into the values would be a
# category error: this endpoint tests plumbing, not analysis.
#
# Arbitrary caller-supplied schemas are not accepted over HTTP at this phase.
# Internal Python callers pass any approved Pydantic model directly to the
# service.
#
# The rationale lives in this comment rather than in the class docstring because
# a docstring becomes the JSON Schema's ``description``, and the schema is sent
# to the model. Several hundred characters of internal reasoning would be spent
# from the context window of a small model to tell it something it must not act
# on. Descriptions here are written *for the model* and kept short.
class SmokeTestSchema(BaseModel):
    """A short summary of the input text."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="A short title summarising the input text.")
    keywords: list[str] = Field(description="One to five salient keywords.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        # Spelled out because a numeric range in JSON Schema is *not* enforced by
        # Ollama's constrained decoding: it guarantees an object with a number
        # here, not a number within bounds. Observed in Phase 4A-1 validation,
        # where qwen2.5:1.5b returned 3. Post-validation rejects that - the range
        # is only advisory to the model, never to us.
        description="A number between 0.0 and 1.0 inclusive.",
    )


class DiagnosticStructuredRequest(BaseModel):
    """One bounded structured generation against :class:`SmokeTestSchema`."""

    model_config = ConfigDict(extra="forbid")

    prompt: Prompt
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1, le=4096)
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)

    _prompt_not_blank = field_validator("prompt")(lambda value: _reject_blank(value))


class DiagnosticStructuredResponse(BaseModel):
    """The validated structured value plus how it was produced.

    ``result`` is the parsed and schema-validated object, not the raw text. The
    raw text is not returned: it would be the one place in this API where
    unvalidated model output is echoed back verbatim.
    """

    result: SmokeTestSchema
    metadata: GenerationMetadataResponse
