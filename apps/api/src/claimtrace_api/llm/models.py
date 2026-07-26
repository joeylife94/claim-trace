"""Provider-neutral request and response types.

These are plain frozen dataclasses. Nothing here imports FastAPI, SQLAlchemy, or
httpx, and nothing here knows what a claim is: a provider takes messages and
returns text plus metadata, and that is the entire vocabulary the boundary needs.

A request validates itself on construction. The alternative - letting a malformed
message list reach an adapter and be rejected differently by each one - is how a
"boundary" stops being one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import StrEnum

from claimtrace_api.llm.errors import LLMInvalidRequestError

#: Absolute ceilings, independent of configuration. Settings may lower these; no
#: setting may raise them, because they exist to keep a diagnostics endpoint from
#: being turned into an unbounded compute sink.
MAX_TEMPERATURE = 2.0
MAX_OUTPUT_TOKENS_LIMIT = 4096
MAX_TIMEOUT_SECONDS = 600.0
MAX_STOP_SEQUENCES = 8


class MessageRole(StrEnum):
    """The roles this boundary accepts.

    Deliberately three. ``tool`` and ``function`` are absent because tool calling
    is out of scope for this phase, and an enum that admits a role no adapter
    implements is a promise the boundary does not keep.
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class FinishReason(StrEnum):
    """Why generation stopped."""

    #: The model finished on its own, or hit a stop sequence.
    STOP = "stop"
    #: The output token limit was reached. Structured output is very likely
    #: truncated, which is why the JSON parser reports truncation distinctly.
    LENGTH = "length"
    #: The provider suppressed the output.
    CONTENT_FILTER = "content_filter"
    #: The provider reported a reason this adapter does not model.
    UNKNOWN = "unknown"


class StructuredOutputMode(StrEnum):
    """How strongly a provider can constrain JSON output.

    Ordered by strength. The service picks the strongest mode a provider both
    supports *and* has been configured for; it never assumes a stronger one.
    """

    #: The provider enforces a full JSON Schema server-side. Output is
    #: structurally guaranteed before it reaches us.
    NATIVE_JSON_SCHEMA = "native_json_schema"
    #: The provider guarantees syntactically valid JSON, but not our schema.
    #: Parsing cannot fail; validation still can.
    NATIVE_JSON_OBJECT = "native_json_object"
    #: Nothing is enforced. The schema is described in the prompt and the answer
    #: is validated strictly on arrival. Always reported as a warning.
    PROMPT_CONSTRAINED_JSON = "prompt_constrained_json"
    #: Structured output is not available from this provider at all.
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class Message:
    """One turn of a conversation.

    Content is required to be non-blank: an empty turn is silently dropped by
    some servers and rejected by others, and neither is a behaviour worth
    inheriting.
    """

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise LLMInvalidRequestError(f"A {self.role.value} message may not be empty.")


@dataclass(frozen=True, slots=True)
class GenerationOptions:
    """Sampling and limit controls, separated from the conversation itself.

    Every field is optional. ``None`` means "the provider's default", which is
    not the same as a zero: ``temperature=0.0`` requests greedy decoding, while
    ``temperature=None`` leaves whatever the server was started with.
    """

    temperature: float | None = None
    max_output_tokens: int | None = None
    stop: tuple[str, ...] = ()
    #: Honoured only where :attr:`ProviderCapabilities.supports_seed` is true.
    #: Requesting one elsewhere is not an error; it is reported as a warning on
    #: the response, because silently ignoring a determinism request is worse.
    seed: int | None = None
    #: Overall deadline for the whole call, retries included. Bounded by
    #: configuration at the service layer; bounded absolutely here.
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.temperature is not None and not 0.0 <= self.temperature <= MAX_TEMPERATURE:
            raise LLMInvalidRequestError(f"temperature must be between 0.0 and {MAX_TEMPERATURE}.")
        if self.max_output_tokens is not None and not (
            0 < self.max_output_tokens <= MAX_OUTPUT_TOKENS_LIMIT
        ):
            raise LLMInvalidRequestError(
                f"max_output_tokens must be between 1 and {MAX_OUTPUT_TOKENS_LIMIT}."
            )
        if self.timeout_seconds is not None and not (
            0 < self.timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise LLMInvalidRequestError(
                f"timeout_seconds must be between 0 and {MAX_TIMEOUT_SECONDS}."
            )
        if len(self.stop) > MAX_STOP_SEQUENCES:
            raise LLMInvalidRequestError(
                f"At most {MAX_STOP_SEQUENCES} stop sequences are supported."
            )
        if any(not sequence for sequence in self.stop):
            raise LLMInvalidRequestError("A stop sequence may not be empty.")


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """One generation, described independently of any provider.

    The message sequence is constrained rather than free-form:

    * at least one message, because there is otherwise nothing to answer;
    * at most one system message, and only in first position, because every
      target server treats a mid-conversation system turn differently;
    * the last message is from the user, because a request ending on an
      assistant turn is asking the model to continue its own text - a different
      operation that this phase does not offer.

    Note what is *absent*: there is no model field. The model comes from server
    configuration and cannot be selected per request, so a caller reaching the
    diagnostics endpoint cannot point the deployment at an arbitrary model.
    """

    messages: tuple[Message, ...]
    options: GenerationOptions = field(default_factory=GenerationOptions)
    #: Correlates log lines for one logical operation. Not a secret and not
    #: user-supplied text; generated by the service when absent.
    request_id: str | None = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise LLMInvalidRequestError("At least one message is required.")

        roles = [message.role for message in self.messages]

        system_positions = [i for i, role in enumerate(roles) if role is MessageRole.SYSTEM]
        if len(system_positions) > 1:
            raise LLMInvalidRequestError("At most one system message is supported.")
        if system_positions and system_positions[0] != 0:
            raise LLMInvalidRequestError("A system message must be the first message.")

        if roles[-1] is not MessageRole.USER:
            raise LLMInvalidRequestError("The last message must be a user message.")

    @property
    def system_message(self) -> Message | None:
        """The leading system turn, when there is one."""
        first = self.messages[0]
        return first if first.role is MessageRole.SYSTEM else None

    @property
    def conversation(self) -> tuple[Message, ...]:
        """Everything except a leading system turn.

        Ollama's ``/api/chat`` takes the system message inline, while its
        ``/api/generate`` takes it separately. Splitting here keeps that choice
        inside the adapter.
        """
        return self.messages[1:] if self.system_message else self.messages

    @property
    def prompt_characters(self) -> int:
        """Total characters across all message content.

        A size, not content: safe to log, and the field an operator needs to
        recognise a request that was too large.
        """
        return sum(len(message.content) for message in self.messages)

    def with_options(self, options: GenerationOptions) -> GenerationRequest:
        """Return a copy carrying different options."""
        return replace(self, options=options)

    def log_fields(self) -> dict[str, object]:
        """The safe description of this request.

        Counts and limits only. No message content of any kind appears here, and
        that is the whole point of the method existing.
        """
        return {
            "request_id": self.request_id,
            "message_count": len(self.messages),
            "prompt_characters": self.prompt_characters,
            "has_system_message": self.system_message is not None,
            "temperature": self.options.temperature,
            "max_output_tokens": self.options.max_output_tokens,
            "seed": self.options.seed,
            "timeout_seconds": self.options.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token counts, each independently optional.

    Every field is nullable because "the provider did not tell us" is a real and
    common state, and reporting it as ``0`` would be a fabricated measurement.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    @classmethod
    def create(
        cls,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> TokenUsage:
        """Build usage, deriving the total only when both parts are known."""
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        return cls(
            input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens
        )

    @property
    def is_empty(self) -> bool:
        return self.input_tokens is None and self.output_tokens is None


@dataclass(frozen=True, slots=True)
class GenerationResponse:
    """The result of one generation.

    ``warnings`` is where a degraded capability becomes visible: a prompt-only
    JSON fallback, or a seed that was requested and could not be honoured. A
    caller that ignores warnings still gets a correct answer; a caller that reads
    them can tell how strongly it was enforced.
    """

    text: str
    provider: str
    model: str
    model_version: str | None = None
    finish_reason: FinishReason = FinishReason.UNKNOWN
    usage: TokenUsage = field(default_factory=TokenUsage)
    duration_seconds: float = 0.0
    #: The provider's own identifier for this request, when it supplies one.
    provider_request_id: str | None = None
    #: How JSON was constrained, on a structured call. ``None`` on a plain call.
    structured_output_mode: StructuredOutputMode | None = None
    warnings: tuple[str, ...] = ()
    #: How many attempts were made, including the successful one.
    attempts: int = 1

    def with_warning(self, warning: str) -> GenerationResponse:
        """Return a copy carrying one more warning, preserving order."""
        if warning in self.warnings:
            return self
        return replace(self, warnings=(*self.warnings, warning))

    def log_fields(self) -> dict[str, object]:
        """The safe description of this response - never the generated text."""
        return {
            "provider": self.provider,
            "model": self.model,
            "model_version": self.model_version,
            "finish_reason": self.finish_reason.value,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "total_tokens": self.usage.total_tokens,
            "duration_seconds": round(self.duration_seconds, 4),
            "response_characters": len(self.text),
            "attempts": self.attempts,
            "structured_output_mode": (
                self.structured_output_mode.value if self.structured_output_mode else None
            ),
            "warning_count": len(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """What a provider has been validated to do.

    Every flag defaults to *unsupported*. A capability is turned on only where
    the adapter implements it against a documented API and a test covers it -
    "the server might support this" is not a capability, because the service
    above uses these flags to decide whether an answer can be trusted.
    """

    supports_text_generation: bool = True
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.UNSUPPORTED
    supports_seed: bool = False
    supports_usage_metadata: bool = False
    supports_model_listing: bool = False
    #: Out of scope for this phase. Present in the contract so that adding it
    #: later is a capability flip rather than a new concept.
    supports_streaming: bool = False

    @property
    def supports_structured_output(self) -> bool:
        return self.structured_output_mode is not StructuredOutputMode.UNSUPPORTED

    @property
    def structured_output_is_native(self) -> bool:
        """Whether the *server* enforces JSON, rather than the prompt asking for it."""
        return self.structured_output_mode in (
            StructuredOutputMode.NATIVE_JSON_SCHEMA,
            StructuredOutputMode.NATIVE_JSON_OBJECT,
        )


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    """Identity and configuration of a provider, with nothing sensitive in it.

    ``base_url`` is passed through :func:`safe_base_url` before it gets here, so
    a URL carrying credentials cannot reach a response body or a log line.
    """

    provider: str
    model: str
    base_url: str | None = None
    model_version: str | None = None
    #: ``http``, ``https``, or ``in-process`` for the fake provider.
    transport: str = "http"
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """The outcome of one availability check.

    ``available`` and ``model_available`` are separate because they fail
    separately and are fixed differently: an unreachable server is an
    infrastructure problem, a missing model tag is one ``ollama pull`` away.
    """

    available: bool
    model_available: bool = False
    #: Safe, operator-facing summary. Never a provider payload.
    detail: str = ""
    error_code: str | None = None
    #: How long the check took, so a "healthy but slow" provider is visible.
    duration_seconds: float = 0.0


_CREDENTIALS = re.compile(r"^(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?:[^/@]*@)")


def safe_base_url(url: str | None) -> str | None:
    """Strip any userinfo from a URL so it can be shown and logged.

    ``http://user:secret@host:11434`` becomes ``http://host:11434``. Applied at
    every boundary that renders a base URL rather than trusted to the caller,
    because the one place it gets forgotten is the one that leaks.
    """
    if not url:
        return url
    return _CREDENTIALS.sub(r"\g<scheme>", url)
