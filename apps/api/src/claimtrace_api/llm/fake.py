"""A deterministic provider that talks to nothing.

Like the fake embedding provider, this is a real implementation of the protocol
rather than a mock: it runs the same request validation, the same JSON
extraction, and the same schema validation as the network adapters, and only the
transport is replaced. That is what makes it worth having - a test that passes
against it has exercised every layer except the socket.

It is also the provider a developer can run the entire application against with
no model downloaded and no Ollama installed, which keeps ``LLM_PROVIDER=fake`` an
honest default for CI and for offline work.

Everything a test needs to steer is a constructor argument: the text to return,
a raw string to return for structured calls (so malformed JSON and schema
mismatches are reachable), an error to raise, how many times to raise it before
succeeding, and how long to take. Nothing is monkey-patched.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from claimtrace_api.llm.base import StructuredGeneration
from claimtrace_api.llm.errors import LLMError, LLMUnsupportedCapabilityError
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
)

PROVIDER_NAME = "fake"

DEFAULT_TEXT = "This is a deterministic response from the fake LLM provider."


@dataclass(frozen=True, slots=True)
class RecordedCall:
    """One call, kept so a test can assert what the layer above actually sent."""

    kind: str  # "generate" | "generate_structured" | "check_health"
    request: GenerationRequest | None = None
    output_model: type[BaseModel] | None = None
    attempt: int = 1


@dataclass
class FakeLLMProvider:
    """A provider with scripted answers and recorded calls.

    Args:
        text: plain-text reply. A sequence is consumed one entry per call, so a
            test can script a conversation; the last entry repeats once
            exhausted.
        structured_text: raw text returned by structured calls, *before*
            parsing. Set it to malformed JSON or to a valid-JSON-wrong-shape
            payload to drive those failure paths through the real pipeline.
            A sequence is consumed one entry per call and its last entry
            repeats, exactly like ``text`` - which is how a test scripts a
            rejected answer followed by a corrected one, and therefore how the
            grounded repair path is exercised with no model and no network.
            When ``None``, a payload satisfying the requested schema is
            synthesised, which is what makes the fake usable end to end.
        fail_with: error raised instead of answering.
        fail_times: how many calls ``fail_with`` applies to before the provider
            starts succeeding. ``None`` means every call fails. Used to test the
            retry policy against a transient failure.
        delay_seconds: awaited before answering. Gives timeout and cancellation
            tests something real to interrupt.
        healthy / model_available: what :meth:`check_health` reports.
    """

    text: str | Sequence[str] = DEFAULT_TEXT
    structured_text: str | Sequence[str] | None = None
    model: str = "fake-model"
    model_version: str = "1"
    fail_with: LLMError | None = None
    fail_times: int | None = None
    delay_seconds: float = 0.0
    healthy: bool = True
    model_available: bool = True
    capabilities: ProviderCapabilities = field(
        default_factory=lambda: ProviderCapabilities(
            supports_text_generation=True,
            structured_output_mode=StructuredOutputMode.NATIVE_JSON_SCHEMA,
            supports_seed=True,
            supports_usage_metadata=True,
            supports_model_listing=True,
            supports_streaming=False,
        )
    )
    #: Every call, in order. Inspected by tests; ignored by everything else.
    calls: list[RecordedCall] = field(default_factory=list)
    _generation_count: int = field(default=0, init=False)

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider=PROVIDER_NAME,
            model=self.model,
            base_url=None,
            model_version=self.model_version,
            transport="in-process",
            capabilities=self.capabilities,
        )

    async def check_health(self) -> HealthStatus:
        self.calls.append(RecordedCall(kind="check_health"))
        return HealthStatus(
            available=self.healthy,
            model_available=self.healthy and self.model_available,
            detail=(
                "Fake provider is always reachable."
                if self.healthy
                else "Fake provider is configured as unavailable."
            ),
            error_code=None if self.healthy else "llm_provider_unavailable",
        )

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        self._generation_count += 1
        attempt = self._generation_count
        self.calls.append(RecordedCall(kind="generate", request=request, attempt=attempt))

        started = time.perf_counter()
        await self._pause()
        self._maybe_fail(attempt)

        text = self._next_text(attempt)
        return self._response(
            text=text,
            request=request,
            duration=time.perf_counter() - started,
            structured_mode=None,
        )

    async def generate_structured[SchemaT: BaseModel](
        self, request: GenerationRequest, output_model: type[SchemaT]
    ) -> StructuredGeneration[SchemaT]:
        if not self.capabilities.supports_structured_output:
            raise LLMUnsupportedCapabilityError(
                "The fake provider is configured without structured output support.",
                provider=PROVIDER_NAME,
                model=self.model,
            )

        self._generation_count += 1
        attempt = self._generation_count
        self.calls.append(
            RecordedCall(
                kind="generate_structured",
                request=request,
                output_model=output_model,
                attempt=attempt,
            )
        )

        started = time.perf_counter()
        await self._pause()
        self._maybe_fail(attempt)

        raw = self._next_structured_text(attempt, output_model)

        # Deliberately the same parser the real adapters use. A test that feeds
        # this provider malformed JSON is testing the production pipeline, not a
        # second implementation of it.
        value = parse_structured_output(raw, output_model)

        response = self._response(
            text=raw,
            request=request,
            duration=time.perf_counter() - started,
            structured_mode=self.capabilities.structured_output_mode,
        )
        return StructuredGeneration(value=value, response=response)

    async def aclose(self) -> None:
        """No transport to release."""

    # -- internals ----------------------------------------------------------

    async def _pause(self) -> None:
        """Sleep, if configured. The seam cancellation tests interrupt."""
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

    def _maybe_fail(self, attempt: int) -> None:
        if self.fail_with is None:
            return
        if self.fail_times is None or attempt <= self.fail_times:
            raise self.fail_with

    def _next_text(self, attempt: int) -> str:
        if isinstance(self.text, str):
            return self.text
        if not self.text:
            return ""
        return self._scripted(self.text, attempt)

    def _next_structured_text(self, attempt: int, output_model: type[BaseModel]) -> str:
        if self.structured_text is None:
            return _synthesize_json(json_schema_for(output_model))
        if isinstance(self.structured_text, str):
            return self.structured_text
        if not self.structured_text:
            return ""
        return self._scripted(self.structured_text, attempt)

    @staticmethod
    def _scripted(entries: Sequence[str], attempt: int) -> str:
        # Clamps rather than wraps: a scripted sequence that runs out should keep
        # answering with its final entry, not silently restart from the top.
        return entries[min(attempt - 1, len(entries) - 1)]

    def _response(
        self,
        *,
        text: str,
        request: GenerationRequest,
        duration: float,
        structured_mode: StructuredOutputMode | None,
    ) -> GenerationResponse:
        # Character-count based, deterministic, and clearly synthetic. Enough for
        # a caller to prove it reads usage; never mistakable for a real count.
        input_tokens = max(1, request.prompt_characters // 4)
        output_tokens = max(1, len(text) // 4)

        return GenerationResponse(
            text=text,
            provider=PROVIDER_NAME,
            model=self.model,
            model_version=self.model_version,
            finish_reason=FinishReason.STOP,
            usage=TokenUsage.create(input_tokens=input_tokens, output_tokens=output_tokens),
            duration_seconds=duration,
            provider_request_id=f"fake-{self._generation_count}",
            structured_output_mode=structured_mode,
        )


def _synthesize_json(schema: dict[str, Any]) -> str:
    """Build a minimal JSON document satisfying ``schema``.

    Covers the subset of JSON Schema that Pydantic emits for the kind of narrow
    output models this boundary is used with. It exists so the fake provider can
    answer a structured request for *any* schema, which is what lets the whole
    application - diagnostics endpoint included - run with no model present.
    """
    return json.dumps(_synthesize_value(schema, schema), ensure_ascii=False)


def _synthesize_value(schema: dict[str, Any], root: dict[str, Any]) -> Any:
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], root)

    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]

    # A declared example is by construction a legal value, which is more than
    # can be derived from a `pattern`: synthesising a string that satisfies an
    # arbitrary regex is not something this function should attempt, and getting
    # it subtly wrong would make the fake provider fail schemas the real ones
    # satisfy. Schemas that constrain a string's shape declare an example for
    # exactly this reason - see the evidence id field in grounding/draft.py.
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]

    # anyOf/oneOf appear for optional fields; the first non-null branch is the
    # one that exercises the schema rather than sidestepping it.
    for key in ("anyOf", "oneOf"):
        if key in schema:
            branches = [b for b in schema[key] if b.get("type") != "null"]
            if branches:
                return _synthesize_value(branches[0], root)
            return None

    match schema.get("type"):
        case "object":
            properties: dict[str, Any] = schema.get("properties", {})
            required = schema.get("required", list(properties))
            return {
                name: _synthesize_value(properties[name], root)
                for name in required
                if name in properties
            }
        case "array":
            items = schema.get("items")
            return [_synthesize_value(items, root)] if isinstance(items, dict) else []
        case "integer":
            return 1
        case "number":
            return 0.5
        case "boolean":
            return True
        case "null":
            return None
        case _:
            return "sample"


def _resolve_ref(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    """Resolve a local ``#/$defs/Name`` reference. Only local refs are emitted."""
    node: Any = root
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(node, dict) or part not in node:
            return {}
        node = node[part]
    return node if isinstance(node, dict) else {}
