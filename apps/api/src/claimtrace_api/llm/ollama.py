"""Ollama provider.

Speaks Ollama's documented HTTP API directly: ``GET /api/tags`` to enumerate
installed models and ``POST /api/chat`` with ``stream: false`` to generate.

Structured output uses Ollama's ``format`` parameter, which since v0.5 accepts a
full JSON Schema and constrains decoding to it server-side. That is a genuine
native-schema capability, not a prompt convention, so this adapter reports
:attr:`~claimtrace_api.llm.models.StructuredOutputMode.NATIVE_JSON_SCHEMA` - and
the returned text is still parsed and validated exactly as strictly as a
prompt-constrained reply would be. Enforcement upstream is a reason to expect
valid output, never a reason to skip checking it.

The adapter never logs a prompt, a reply, or a provider payload. Ollama echoes
neither credentials nor headers in its error bodies, but the body is still not
rendered into an exception message: errors are *classified* from it, and the
message this adapter emits is written here from configuration it already knows.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Final

import httpx
from pydantic import BaseModel

from claimtrace_api.llm.base import StructuredGeneration
from claimtrace_api.llm.errors import (
    LLMAuthenticationError,
    LLMContextLengthExceededError,
    LLMError,
    LLMInternalProviderError,
    LLMInvalidRequestError,
    LLMInvalidResponseError,
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMRateLimitedError,
)
from claimtrace_api.llm.json_output import json_schema_for, parse_structured_output
from claimtrace_api.llm.models import (
    FinishReason,
    GenerationRequest,
    GenerationResponse,
    HealthStatus,
    ProviderCapabilities,
    ProviderMetadata,
    StructuredOutputMode,
    TokenUsage,
    safe_base_url,
)
from claimtrace_api.llm.retry import RetryPolicy
from claimtrace_api.llm.transport import (
    TimeoutConfig,
    map_transport_error,
    retry_after_seconds,
    run_bounded,
    validate_base_url,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "ollama"

_CHAT_PATH: Final = "/api/chat"
_TAGS_PATH: Final = "/api/tags"

#: Substrings that identify a context-window rejection. Matched against the
#: provider's error text only to *classify* it - the text itself never reaches a
#: message, a log line, or a response body.
_CONTEXT_LENGTH_MARKERS: Final = ("context length", "context window", "too many tokens")
_NOT_FOUND_MARKERS: Final = ("not found", "no such model", "pull the model")


class OllamaProvider:
    """Generates text with a local Ollama server."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeouts: TimeoutConfig | None = None,
        retry_policy: RetryPolicy | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = validate_base_url(base_url, setting_name="LLM_OLLAMA_BASE_URL")
        self._model = model
        self._timeouts = timeouts or TimeoutConfig()
        self._retry_policy = retry_policy or RetryPolicy()
        # Injected by tests with a mock transport; built lazily otherwise so
        # constructing the provider - which happens at startup, always - never
        # opens a socket or requires Ollama to be running.
        self._client = client
        self._owns_client = client is None
        #: Learned from ``/api/tags`` on the first health check. Ollama's model
        #: name is a mutable tag, so the digest is what actually identifies the
        #: weights that answered.
        self._model_digest: str | None = None

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider=PROVIDER_NAME,
            model=self._model,
            base_url=safe_base_url(self._base_url),
            model_version=self._model_digest,
            transport="http",
            capabilities=ProviderCapabilities(
                supports_text_generation=True,
                # Ollama constrains decoding to a supplied JSON Schema.
                structured_output_mode=StructuredOutputMode.NATIVE_JSON_SCHEMA,
                supports_seed=True,
                supports_usage_metadata=True,
                supports_model_listing=True,
                # Deliberately false: /api/chat supports streaming, this adapter
                # does not implement it, and a capability describes what the
                # adapter has been validated to do.
                supports_streaming=False,
            ),
        )

    async def check_health(self) -> HealthStatus:
        """Reachability and whether the configured tag is installed.

        Never raises: an unreachable Ollama is a state the status endpoint has to
        render, not an exception it has to survive.
        """
        started = time.perf_counter()
        try:
            models = await self._list_models()
        except LLMError as error:
            return HealthStatus(
                available=False,
                model_available=False,
                detail="The Ollama server could not be reached.",
                error_code=error.code.value,
                duration_seconds=time.perf_counter() - started,
            )

        installed = self._find_model(models)
        if installed is None:
            return HealthStatus(
                available=True,
                model_available=False,
                detail=(
                    f"Ollama is reachable but the model '{self._model}' is not "
                    f"installed. Pull it with: ollama pull {self._model}"
                ),
                error_code="llm_model_not_found",
                duration_seconds=time.perf_counter() - started,
            )

        digest = installed.get("digest")
        if isinstance(digest, str):
            self._model_digest = digest[:12]

        return HealthStatus(
            available=True,
            model_available=True,
            detail=f"Ollama is reachable and '{self._model}' is installed.",
            duration_seconds=time.perf_counter() - started,
        )

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        _, response = await self._run(request, output_model=None)
        return response

    async def generate_structured[SchemaT: BaseModel](
        self, request: GenerationRequest, output_model: type[SchemaT]
    ) -> StructuredGeneration[SchemaT]:
        text, response = await self._run(request, output_model=output_model)
        # Validated even though Ollama enforced the schema during decoding: an
        # older server silently ignores an unknown `format`, and a truncated
        # reply is still truncated. Trust, then verify.
        value = parse_structured_output(text, output_model)
        return StructuredGeneration(value=value, response=response)

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    # -- generation ---------------------------------------------------------

    async def _run(
        self, request: GenerationRequest, *, output_model: type[BaseModel] | None
    ) -> tuple[str, GenerationResponse]:
        """Bound the whole operation, retries included, then execute it."""
        timeouts = self._timeouts.bounded_by(request.options.timeout_seconds)
        payload = self._chat_payload(request, output_model=output_model)

        log_context = {
            "provider": PROVIDER_NAME,
            "model": self._model,
            "structured": output_model is not None,
            **request.log_fields(),
        }
        started = time.perf_counter()

        body, attempts = await run_bounded(
            lambda _attempt: self._post_chat(payload, timeouts),
            timeouts=timeouts,
            policy=self._retry_policy,
            provider=PROVIDER_NAME,
            model=self._model,
            log_context=log_context,
        )

        duration = time.perf_counter() - started
        text = self._extract_text(body)
        response = self._build_response(
            text=text,
            body=body,
            duration=duration,
            attempts=attempts,
            request=request,
            output_model=output_model,
        )
        logger.info("llm generation completed", extra={**log_context, **response.log_fields()})
        return text, response

    async def _post_chat(self, payload: dict[str, Any], timeouts: TimeoutConfig) -> dict[str, Any]:
        client = self._ensure_client()
        try:
            response = await client.post(_CHAT_PATH, json=payload, timeout=timeouts.to_httpx())
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, provider=PROVIDER_NAME, model=self._model) from exc

        if response.status_code >= 400:
            raise self._map_status_error(response)

        return self._decode_json(response)

    def _chat_payload(
        self, request: GenerationRequest, *, output_model: type[BaseModel] | None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            # This adapter reads one JSON document per response. Streaming is a
            # separate transport, not a flag to flip here.
            "stream": False,
        }

        options: dict[str, Any] = {}
        if request.options.temperature is not None:
            options["temperature"] = request.options.temperature
        if request.options.max_output_tokens is not None:
            options["num_predict"] = request.options.max_output_tokens
        if request.options.seed is not None:
            options["seed"] = request.options.seed
        if request.options.stop:
            options["stop"] = list(request.options.stop)
        if options:
            payload["options"] = options

        if output_model is not None:
            payload["format"] = json_schema_for(output_model)

        return payload

    # -- response parsing ---------------------------------------------------

    def _extract_text(self, body: dict[str, Any]) -> str:
        message = body.get("message")
        if not isinstance(message, dict):
            raise LLMInvalidResponseError(
                "The Ollama response did not contain a message.",
                provider=PROVIDER_NAME,
                model=self._model,
            )
        content = message.get("content")
        if not isinstance(content, str):
            raise LLMInvalidResponseError(
                "The Ollama response did not contain message content.",
                provider=PROVIDER_NAME,
                model=self._model,
            )
        return content

    def _build_response(
        self,
        *,
        text: str,
        body: dict[str, Any],
        duration: float,
        attempts: int,
        request: GenerationRequest,
        output_model: type[BaseModel] | None,
    ) -> GenerationResponse:
        response = GenerationResponse(
            text=text,
            provider=PROVIDER_NAME,
            model=str(body.get("model") or self._model),
            model_version=self._model_digest,
            finish_reason=_finish_reason(body.get("done_reason")),
            usage=TokenUsage.create(
                input_tokens=_optional_int(body.get("prompt_eval_count")),
                output_tokens=_optional_int(body.get("eval_count")),
            ),
            duration_seconds=duration,
            provider_request_id=None,
            structured_output_mode=(
                StructuredOutputMode.NATIVE_JSON_SCHEMA if output_model is not None else None
            ),
            attempts=attempts,
        )

        if response.finish_reason is FinishReason.LENGTH:
            response = response.with_warning(
                "Generation stopped at the output token limit; the result may be incomplete."
            )
        if request.options.seed is not None and request.options.temperature not in (None, 0.0):
            response = response.with_warning(
                "A seed was requested with a non-zero temperature; output is reproducible "
                "only when temperature is 0."
            )
        return response

    # -- model listing ------------------------------------------------------

    async def _list_models(self) -> list[dict[str, Any]]:
        client = self._ensure_client()
        try:
            response = await client.get(
                _TAGS_PATH,
                timeout=httpx.Timeout(
                    connect=self._timeouts.connect_seconds,
                    read=self._timeouts.connect_seconds,
                    write=self._timeouts.connect_seconds,
                    pool=self._timeouts.connect_seconds,
                ),
            )
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, provider=PROVIDER_NAME, model=self._model) from exc

        if response.status_code >= 400:
            raise self._map_status_error(response)

        body = self._decode_json(response)
        models = body.get("models")
        if not isinstance(models, list):
            raise LLMInvalidResponseError(
                "The Ollama model list had an unexpected shape.",
                provider=PROVIDER_NAME,
                model=self._model,
            )
        return [item for item in models if isinstance(item, dict)]

    def _find_model(self, models: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Locate the configured tag among installed models.

        Ollama reports ``llama3.2:latest`` for a model pulled as ``llama3.2``, so
        a bare name is compared against the ``:latest`` form as well - otherwise
        the most common way to pull a model reports as missing.
        """
        wanted = {self._model}
        if ":" not in self._model:
            wanted.add(f"{self._model}:latest")

        for entry in models:
            for key in ("name", "model"):
                value = entry.get(key)
                if isinstance(value, str) and value in wanted:
                    return entry
        return None

    # -- errors -------------------------------------------------------------

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeouts.to_httpx()
            )
        return self._client

    def _decode_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise LLMInvalidResponseError(
                "The Ollama server returned a response that is not JSON.",
                provider=PROVIDER_NAME,
                model=self._model,
                status=response.status_code,
            ) from exc

        if not isinstance(body, dict):
            raise LLMInvalidResponseError(
                "The Ollama server returned an unexpected response shape.",
                provider=PROVIDER_NAME,
                model=self._model,
                status=response.status_code,
            )
        return body

    def _map_status_error(self, response: httpx.Response) -> LLMError:
        """Map an HTTP status onto the taxonomy.

        The provider's error text is read to *classify* the failure and is then
        discarded; every message returned from here is written from values this
        adapter already holds. That is what keeps a prompt echoed back inside an
        error body from travelling any further.
        """
        status = response.status_code
        detail = _error_text(response).lower()
        common = {"provider": PROVIDER_NAME, "model": self._model, "status": status}

        if status == 404 or any(marker in detail for marker in _NOT_FOUND_MARKERS):
            return LLMModelNotFoundError(
                f"The model '{self._model}' is not installed on the Ollama server. "
                f"Pull it with: ollama pull {self._model}",
                **common,
            )
        if status in (401, 403):
            return LLMAuthenticationError(
                "The Ollama server rejected the request as unauthorised.", **common
            )
        if status == 429:
            return LLMRateLimitedError(
                "The Ollama server is rate limiting requests.",
                retry_after_seconds=retry_after_seconds(response),
                **common,
            )
        if status == 400:
            if any(marker in detail for marker in _CONTEXT_LENGTH_MARKERS):
                return LLMContextLengthExceededError(
                    "The prompt exceeds the model's context window.", **common
                )
            return LLMInvalidRequestError(
                "The Ollama server rejected the request as invalid.", **common
            )
        if status in (502, 503, 504):
            return LLMProviderUnavailableError(
                "The Ollama server is not ready to serve requests.",
                retry_after_seconds=retry_after_seconds(response),
                **common,
            )
        if any(marker in detail for marker in _CONTEXT_LENGTH_MARKERS):
            return LLMContextLengthExceededError(
                "The prompt exceeds the model's context window.", **common
            )
        return LLMInternalProviderError(
            f"The Ollama server returned an error (HTTP {status}).", **common
        )


def _error_text(response: httpx.Response) -> str:
    """Ollama's ``{"error": "..."}`` string, for classification only."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, str):
            return error
    return ""


def _finish_reason(raw: object) -> FinishReason:
    match raw:
        case "stop":
            return FinishReason.STOP
        case "length":
            return FinishReason.LENGTH
        case _:
            return FinishReason.UNKNOWN


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
