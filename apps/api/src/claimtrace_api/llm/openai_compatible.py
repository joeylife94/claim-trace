"""OpenAI-compatible provider, for local servers such as vLLM.

The target is a model server *on your own network* that happens to speak the
OpenAI chat-completions wire format - vLLM, llama.cpp's server, LM Studio, TGI.
The hosted OpenAI service is explicitly not a supported target of this adapter
and is not documented as one: ClaimTrace processes unpublished patent text, and
sending that to a third party is a decision for a deployment to make
deliberately, not something an adapter should make easy by accident.

No vendor SDK. The two endpoints used here - ``POST /chat/completions`` and
``GET /models`` - are a few dozen lines against ``httpx``, and the ``openai``
package would bring a second retry policy, a second timeout model, and a second
exception hierarchy into the one place in this codebase whose job is to have
exactly one of each.

Structured output is *configurable* rather than assumed, because compatibility
here is a spectrum. vLLM enforces a JSON Schema through guided decoding;
llama.cpp's server historically honoured only ``json_object``; some servers
accept ``response_format`` and quietly ignore it. Guessing wrong in the
optimistic direction produces unvalidated output that looks enforced, so the
mode is declared by configuration and the reply is validated regardless.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Final

import httpx
from pydantic import BaseModel, SecretStr

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
    LLMUnsupportedCapabilityError,
)
from claimtrace_api.llm.json_output import (
    json_schema_for,
    parse_structured_output,
    schema_instruction,
)
from claimtrace_api.llm.models import (
    FinishReason,
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
from claimtrace_api.llm.retry import RetryPolicy
from claimtrace_api.llm.transport import (
    TimeoutConfig,
    map_transport_error,
    retry_after_seconds,
    run_bounded,
    validate_base_url,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "openai_compatible"

_CHAT_PATH: Final = "/chat/completions"
_MODELS_PATH: Final = "/models"

_CONTEXT_LENGTH_MARKERS: Final = (
    "context length",
    "context_length_exceeded",
    "maximum context",
    "reduce the length",
)
_MODEL_NOT_FOUND_MARKERS: Final = ("model_not_found", "does not exist", "no such model")

#: The warning attached whenever JSON was requested in the prompt rather than
#: enforced by the server. Surfaced on the response and in the diagnostics UI:
#: a caller must be able to tell the two apart.
PROMPT_CONSTRAINED_WARNING = (
    "Structured output was requested in the prompt rather than enforced by the "
    "server; the response was validated against the schema after the fact."
)


class OpenAICompatibleProvider:
    """Generates text with a local OpenAI-compatible model server."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: SecretStr | None = None,
        structured_output_mode: StructuredOutputMode = StructuredOutputMode.NATIVE_JSON_SCHEMA,
        timeouts: TimeoutConfig | None = None,
        retry_policy: RetryPolicy | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = validate_base_url(base_url, setting_name="LLM_OPENAI_COMPATIBLE_BASE_URL")
        self._model = model
        # Held as a SecretStr for its whole life: it is never placed on the
        # instance as a plain string, never rendered by repr, and reaches str()
        # only inside the header construction below.
        self._api_key = api_key
        self._structured_output_mode = structured_output_mode
        self._timeouts = timeouts or TimeoutConfig()
        self._retry_policy = retry_policy or RetryPolicy()
        self._client = client
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider=PROVIDER_NAME,
            model=self._model,
            base_url=safe_base_url(self._base_url),
            model_version=None,
            transport="http",
            capabilities=ProviderCapabilities(
                supports_text_generation=True,
                structured_output_mode=self._structured_output_mode,
                # Accepted by the wire format and honoured by vLLM. Reported as
                # supported because the field is sent and respected where the
                # server implements it; a server that ignores it produces
                # non-reproducible output, which is why a seed request with a
                # non-zero temperature is warned about on the response.
                supports_seed=True,
                supports_usage_metadata=True,
                supports_model_listing=True,
                supports_streaming=False,
            ),
        )

    async def check_health(self) -> HealthStatus:
        """Reachability, plus whether the configured model is served."""
        started = time.perf_counter()
        try:
            model_ids = await self._list_model_ids()
        except LLMError as error:
            return HealthStatus(
                available=False,
                model_available=False,
                detail="The OpenAI-compatible server could not be reached.",
                error_code=error.code.value,
                duration_seconds=time.perf_counter() - started,
            )

        if self._model not in model_ids:
            return HealthStatus(
                available=True,
                model_available=False,
                detail=(
                    f"The server is reachable but does not serve '{self._model}'. "
                    f"It reports {len(model_ids)} model(s)."
                ),
                error_code="llm_model_not_found",
                duration_seconds=time.perf_counter() - started,
            )

        return HealthStatus(
            available=True,
            model_available=True,
            detail=f"The server is reachable and serves '{self._model}'.",
            duration_seconds=time.perf_counter() - started,
        )

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        _, response = await self._run(request, output_model=None)
        return response

    async def generate_structured[SchemaT: BaseModel](
        self, request: GenerationRequest, output_model: type[SchemaT]
    ) -> StructuredGeneration[SchemaT]:
        if self._structured_output_mode is StructuredOutputMode.UNSUPPORTED:
            raise LLMUnsupportedCapabilityError(
                "This OpenAI-compatible server is configured without structured output support.",
                provider=PROVIDER_NAME,
                model=self._model,
            )

        text, response = await self._run(request, output_model=output_model)
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
        timeouts = self._timeouts.bounded_by(request.options.timeout_seconds)
        payload = self._chat_payload(request, output_model=output_model)

        log_context = {
            "provider": PROVIDER_NAME,
            "model": self._model,
            "structured": output_model is not None,
            "structured_output_mode": (
                self._structured_output_mode.value if output_model is not None else None
            ),
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
        text, finish_reason = self._extract_choice(body)
        response = self._build_response(
            text=text,
            finish_reason=finish_reason,
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
            response = await client.post(
                _CHAT_PATH,
                json=payload,
                headers=self._auth_headers(),
                timeout=timeouts.to_httpx(),
            )
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, provider=PROVIDER_NAME, model=self._model) from exc

        if response.status_code >= 400:
            raise self._map_status_error(response)

        return self._decode_json(response)

    def _chat_payload(
        self, request: GenerationRequest, *, output_model: type[BaseModel] | None
    ) -> dict[str, Any]:
        messages = list(request.messages)

        if output_model is not None and (
            self._structured_output_mode is StructuredOutputMode.PROMPT_CONSTRAINED_JSON
        ):
            # The schema goes into the conversation because the server will not
            # enforce it. Appended as a final user turn rather than merged into
            # the system message: it must survive a request that has no system
            # message, and it must not silently rewrite one the caller supplied.
            messages.append(
                Message(role=MessageRole.USER, content=schema_instruction(output_model))
            )

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": message.role.value, "content": message.content} for message in messages
            ],
            "stream": False,
        }

        if request.options.temperature is not None:
            payload["temperature"] = request.options.temperature
        if request.options.max_output_tokens is not None:
            payload["max_tokens"] = request.options.max_output_tokens
        if request.options.seed is not None:
            payload["seed"] = request.options.seed
        if request.options.stop:
            payload["stop"] = list(request.options.stop)

        if output_model is not None:
            response_format = self._response_format(output_model)
            if response_format is not None:
                payload["response_format"] = response_format

        return payload

    def _response_format(self, output_model: type[BaseModel]) -> dict[str, Any] | None:
        """The ``response_format`` for the configured capability mode.

        ``None`` for the prompt-constrained mode: sending ``response_format`` to
        a server that does not implement it is how an unenforced request comes
        back looking enforced.
        """
        match self._structured_output_mode:
            case StructuredOutputMode.NATIVE_JSON_SCHEMA:
                return {
                    "type": "json_schema",
                    "json_schema": {
                        "name": output_model.__name__,
                        "schema": json_schema_for(output_model),
                        # vLLM's guided decoding honours this; a server that
                        # does not is caught by the validation on arrival.
                        "strict": True,
                    },
                }
            case StructuredOutputMode.NATIVE_JSON_OBJECT:
                return {"type": "json_object"}
            case _:
                return None

    # -- response parsing ---------------------------------------------------

    def _extract_choice(self, body: dict[str, Any]) -> tuple[str, FinishReason]:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMInvalidResponseError(
                "The model server returned no choices.",
                provider=PROVIDER_NAME,
                model=self._model,
            )

        first = choices[0]
        if not isinstance(first, dict):
            raise LLMInvalidResponseError(
                "The model server returned an unexpected choice shape.",
                provider=PROVIDER_NAME,
                model=self._model,
            )

        message = first.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise LLMInvalidResponseError(
                "The model server returned a choice without message content.",
                provider=PROVIDER_NAME,
                model=self._model,
            )

        return message["content"], _finish_reason(first.get("finish_reason"))

    def _build_response(
        self,
        *,
        text: str,
        finish_reason: FinishReason,
        body: dict[str, Any],
        duration: float,
        attempts: int,
        request: GenerationRequest,
        output_model: type[BaseModel] | None,
    ) -> GenerationResponse:
        usage = body.get("usage")
        usage = usage if isinstance(usage, dict) else {}

        response = GenerationResponse(
            text=text,
            provider=PROVIDER_NAME,
            model=str(body.get("model") or self._model),
            model_version=None,
            finish_reason=finish_reason,
            usage=TokenUsage.create(
                input_tokens=_optional_int(usage.get("prompt_tokens")),
                output_tokens=_optional_int(usage.get("completion_tokens")),
                total_tokens=_optional_int(usage.get("total_tokens")),
            ),
            duration_seconds=duration,
            provider_request_id=_optional_str(body.get("id")),
            structured_output_mode=(
                self._structured_output_mode if output_model is not None else None
            ),
            attempts=attempts,
        )

        if output_model is not None and (
            self._structured_output_mode is StructuredOutputMode.PROMPT_CONSTRAINED_JSON
        ):
            response = response.with_warning(PROMPT_CONSTRAINED_WARNING)
        if output_model is not None and (
            self._structured_output_mode is StructuredOutputMode.NATIVE_JSON_OBJECT
        ):
            response = response.with_warning(
                "The server guaranteed valid JSON but did not enforce the schema; "
                "the response was validated against the schema after the fact."
            )
        if finish_reason is FinishReason.LENGTH:
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

    async def _list_model_ids(self) -> set[str]:
        client = self._ensure_client()
        probe_timeout = httpx.Timeout(
            connect=self._timeouts.connect_seconds,
            read=self._timeouts.connect_seconds,
            write=self._timeouts.connect_seconds,
            pool=self._timeouts.connect_seconds,
        )
        try:
            response = await client.get(
                _MODELS_PATH, headers=self._auth_headers(), timeout=probe_timeout
            )
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, provider=PROVIDER_NAME, model=self._model) from exc

        if response.status_code >= 400:
            raise self._map_status_error(response)

        body = self._decode_json(response)
        data = body.get("data")
        if not isinstance(data, list):
            raise LLMInvalidResponseError(
                "The model list had an unexpected shape.",
                provider=PROVIDER_NAME,
                model=self._model,
            )

        return {
            entry["id"]
            for entry in data
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }

    # -- transport ----------------------------------------------------------

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeouts.to_httpx()
            )
        return self._client

    def _auth_headers(self) -> dict[str, str]:
        """Build the Authorization header, if a key is configured.

        Constructed per request and never stored, so the plaintext key exists
        only for the duration of the call and cannot be reached through the
        instance by a repr, a traceback frame, or a debugger dump of state.
        """
        if self._api_key is None:
            return {}
        return {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

    def _decode_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise LLMInvalidResponseError(
                "The model server returned a response that is not JSON.",
                provider=PROVIDER_NAME,
                model=self._model,
                status=response.status_code,
            ) from exc

        if not isinstance(body, dict):
            raise LLMInvalidResponseError(
                "The model server returned an unexpected response shape.",
                provider=PROVIDER_NAME,
                model=self._model,
                status=response.status_code,
            )
        return body

    def _map_status_error(self, response: httpx.Response) -> LLMError:
        """Map an HTTP status and OpenAI-style error body onto the taxonomy.

        The body is read only to classify. It is never quoted: an
        OpenAI-compatible error message routinely echoes part of the offending
        request back, which for this application is patent text.
        """
        status = response.status_code
        detail = _error_text(response).lower()
        common = {"provider": PROVIDER_NAME, "model": self._model, "status": status}

        if status in (401, 403):
            return LLMAuthenticationError(
                "The model server rejected the configured API key.", **common
            )
        if status == 429:
            return LLMRateLimitedError(
                "The model server is rate limiting requests.",
                retry_after_seconds=retry_after_seconds(response),
                **common,
            )
        if status == 404 or any(marker in detail for marker in _MODEL_NOT_FOUND_MARKERS):
            return LLMModelNotFoundError(
                f"The model server does not serve '{self._model}'.", **common
            )
        if any(marker in detail for marker in _CONTEXT_LENGTH_MARKERS):
            return LLMContextLengthExceededError(
                "The prompt exceeds the model's context window.", **common
            )
        if status in (400, 422):
            return LLMInvalidRequestError(
                "The model server rejected the request as invalid.", **common
            )
        if status in (502, 503, 504):
            return LLMProviderUnavailableError(
                "The model server is not ready to serve requests.",
                retry_after_seconds=retry_after_seconds(response),
                **common,
            )
        return LLMInternalProviderError(
            f"The model server returned an error (HTTP {status}).", **common
        )


def _error_text(response: httpx.Response) -> str:
    """The OpenAI-style ``{"error": {...}}`` text, for classification only."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""

    error = body.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        parts = [
            str(error.get(key))
            for key in ("message", "type", "code")
            if isinstance(error.get(key), str)
        ]
        return " ".join(parts)
    return ""


def _finish_reason(raw: object) -> FinishReason:
    match raw:
        case "stop":
            return FinishReason.STOP
        case "length":
            return FinishReason.LENGTH
        case "content_filter":
            return FinishReason.CONTENT_FILTER
        case _:
            return FinishReason.UNKNOWN


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
