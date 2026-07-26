"""The LLM error taxonomy.

Every failure a provider can produce is mapped onto one of these before it
leaves the adapter. Callers branch on :class:`LLMErrorCode`, never on the text of
a message and never on a provider-specific exception type - that is what lets the
service layer treat Ollama, an OpenAI-compatible server, and the fake provider
identically.

Two properties matter more than the taxonomy's shape:

* **Nothing here is a leak.** ``message`` is written for an operator reading a
  diagnostics page. It never carries an API key, an Authorization header, a
  prompt, generated text, or a raw provider payload. The originating exception is
  attached with ``raise ... from`` so a traceback still reaches the log, but it is
  never rendered into the message.
* **Retryability is a property of the failure, not of the caller.** The adapter
  knows whether a 503 came from a busy model server or a mistyped model name; the
  retry policy above it only reads :attr:`LLMError.retryable`.
"""

from __future__ import annotations

from enum import StrEnum


class LLMErrorCode(StrEnum):
    """Stable, client-facing reasons a generation can fail.

    Values are prefixed with ``llm_`` because they share a namespace with the
    ingestion and retrieval codes in :mod:`claimtrace_api.core.errors`, which
    carries the HTTP status for each one.
    """

    #: The selected provider is missing a setting it cannot run without. An
    #: operator problem: no retry and no request will ever succeed until it is
    #: fixed.
    CONFIGURATION_ERROR = "llm_configuration_error"
    #: The provider answered, but reported itself as not ready to serve.
    PROVIDER_UNAVAILABLE = "llm_provider_unavailable"
    #: The connection could not be established at all - nothing was sent.
    CONNECTION_ERROR = "llm_connection_error"
    #: The request exceeded its deadline.
    REQUEST_TIMEOUT = "llm_request_timeout"
    #: The configured model is not present on the provider.
    MODEL_NOT_FOUND = "llm_model_not_found"
    #: The provider rejected our credential.
    AUTHENTICATION_ERROR = "llm_authentication_error"
    #: The provider is rate limiting us.
    RATE_LIMITED = "llm_rate_limited"
    #: Prompt plus requested output exceeds the model's context window.
    CONTEXT_LENGTH_EXCEEDED = "llm_context_length_exceeded"
    #: The request was malformed before it reached the provider, or the provider
    #: rejected it as malformed.
    INVALID_REQUEST = "llm_invalid_request"
    #: The provider answered with a shape this adapter does not recognise.
    INVALID_PROVIDER_RESPONSE = "llm_invalid_provider_response"
    #: Structured output was requested and the model did not return parseable
    #: JSON.
    MALFORMED_JSON = "llm_malformed_json"
    #: JSON parsed, but did not satisfy the requested schema.
    STRUCTURED_OUTPUT_VALIDATION_FAILED = "llm_structured_output_validation_failed"
    #: The awaiting task was cancelled. Distinct from a timeout: nobody is
    #: waiting for the answer any more.
    GENERATION_CANCELLED = "llm_generation_cancelled"
    #: Something was asked of a provider that it has not been validated to do -
    #: schema-constrained output on a server that cannot enforce it, for example.
    UNSUPPORTED_CAPABILITY = "llm_unsupported_capability"
    #: The provider failed internally.
    INTERNAL_PROVIDER_ERROR = "llm_internal_provider_error"


class LLMError(Exception):
    """A generation that could not be completed.

    Subclasses fix :attr:`code`; everything else is per-occurrence. ``provider``
    and ``model`` are optional because a configuration failure can happen before
    either is known.
    """

    #: Set by each subclass. The base class is never raised directly.
    code: LLMErrorCode = LLMErrorCode.INTERNAL_PROVIDER_ERROR
    #: Whether a failure of this kind is worth another attempt by default. An
    #: instance may override it: a 503 from a loading model is retryable, a 503
    #: from a provider that has no such model is not.
    default_retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        status: int | None = None,
        retryable: bool | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.model = model
        #: Upstream HTTP status when one was received. Safe to surface: it is a
        #: number, not a body.
        self.status = status
        self.retryable = self.default_retryable if retryable is None else retryable
        #: Honoured by the retry policy when the provider supplied a Retry-After.
        self.retry_after_seconds = retry_after_seconds

    def __repr__(self) -> str:
        # Deliberately excludes the message: a repr lands in places (task
        # exception logs, pytest output) where the message's provenance has not
        # been reviewed. The code and provider are always safe.
        return (
            f"{type(self).__name__}(code={self.code.value!r}, "
            f"provider={self.provider!r}, retryable={self.retryable!r})"
        )

    def log_fields(self) -> dict[str, object]:
        """The safe subset of this error, for structured logging.

        Excludes the message so a provider string that was never reviewed cannot
        reach the log through an error path.
        """
        return {
            "error_code": self.code.value,
            "provider": self.provider,
            "model": self.model,
            "provider_status": self.status,
            "retryable": self.retryable,
        }


class LLMConfigurationError(LLMError):
    """A required setting for the selected provider is missing or invalid."""

    code = LLMErrorCode.CONFIGURATION_ERROR


class LLMProviderUnavailableError(LLMError):
    """The provider is reachable but not ready to serve."""

    code = LLMErrorCode.PROVIDER_UNAVAILABLE
    default_retryable = True


class LLMConnectionError(LLMError):
    """The connection could not be established.

    Retryable by definition: the request was never delivered, so replaying it
    cannot duplicate work.
    """

    code = LLMErrorCode.CONNECTION_ERROR
    default_retryable = True


class LLMTimeoutError(LLMError):
    """The request exceeded its deadline.

    Not retryable by default. A read timeout means generation may already be
    running on the server; replaying it doubles the load on a model server that
    is, by observation, already too slow.
    """

    code = LLMErrorCode.REQUEST_TIMEOUT


class LLMModelNotFoundError(LLMError):
    """The configured model is not available on the provider."""

    code = LLMErrorCode.MODEL_NOT_FOUND


class LLMAuthenticationError(LLMError):
    """The provider rejected our credential."""

    code = LLMErrorCode.AUTHENTICATION_ERROR


class LLMRateLimitedError(LLMError):
    """The provider is rate limiting us."""

    code = LLMErrorCode.RATE_LIMITED
    default_retryable = True


class LLMContextLengthExceededError(LLMError):
    """The prompt and requested output do not fit the model's context window."""

    code = LLMErrorCode.CONTEXT_LENGTH_EXCEEDED


class LLMInvalidRequestError(LLMError):
    """The request is malformed."""

    code = LLMErrorCode.INVALID_REQUEST


class LLMInvalidResponseError(LLMError):
    """The provider returned a payload this adapter cannot interpret."""

    code = LLMErrorCode.INVALID_PROVIDER_RESPONSE


class LLMMalformedJSONError(LLMError):
    """Structured output was requested and the text returned is not valid JSON."""

    code = LLMErrorCode.MALFORMED_JSON


class LLMStructuredValidationError(LLMError):
    """JSON parsed but did not satisfy the requested schema.

    ``validation_detail`` describes the shape violation - field names and types
    only. It is derived from the *schema*, never from the generated values, so it
    is safe to show while the output that failed is not.
    """

    code = LLMErrorCode.STRUCTURED_OUTPUT_VALIDATION_FAILED

    def __init__(
        self,
        message: str,
        *,
        validation_detail: str = "",
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(message, provider=provider, model=model)
        self.validation_detail = validation_detail


class LLMCancelledError(LLMError):
    """The generation was cancelled before it completed."""

    code = LLMErrorCode.GENERATION_CANCELLED


class LLMUnsupportedCapabilityError(LLMError):
    """The provider has not been validated to do what was asked of it."""

    code = LLMErrorCode.UNSUPPORTED_CAPABILITY


class LLMInternalProviderError(LLMError):
    """The provider failed internally."""

    code = LLMErrorCode.INTERNAL_PROVIDER_ERROR
