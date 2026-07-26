"""The LLM provider contract.

A provider takes messages and returns text plus metadata. It touches no
database, no session, no FastAPI request, and no claim: that is what makes
swapping Ollama for a vLLM server a configuration change rather than an edit to
anything above this line, and what lets the whole test suite run with no model
and no network.

Two methods rather than one for generation, and the split is deliberate.
:meth:`LLMProvider.generate` returns whatever the model said.
:meth:`LLMProvider.generate_structured` returns a *validated instance of a type
the caller named*, or raises. Collapsing them into one method returning ``str``
would push JSON parsing, schema validation, and the choice of how hard to
constrain the model onto every caller, and each caller would get it slightly
wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from claimtrace_api.llm.models import (
    GenerationRequest,
    GenerationResponse,
    HealthStatus,
    ProviderMetadata,
)

# The schema a structured call is validated against is always a Pydantic model.
# Pydantic appears here, at one clearly marked boundary, because it already owns
# schema generation and validation for this project and re-deriving either would
# be strictly worse.


@dataclass(frozen=True, slots=True)
class StructuredGeneration[SchemaT: BaseModel]:
    """A validated structured result together with how it was produced.

    Both halves are returned because both are needed: ``value`` is the answer,
    and ``response`` carries the model, the token usage, the duration, and -
    critically - the warnings that say whether the schema was enforced by the
    server or merely requested in the prompt.
    """

    value: SchemaT
    response: GenerationResponse


@runtime_checkable
class LLMProvider(Protocol):
    """Generates text, and describes what it can be trusted to do."""

    @property
    def name(self) -> str:
        """Stable provider identifier, such as ``ollama``."""

    def get_metadata(self) -> ProviderMetadata:
        """Describe this provider without contacting it.

        Synchronous and side-effect free, so a status endpoint can render
        configuration even when the provider is unreachable. Anything requiring
        the network belongs in :meth:`check_health`.

        The returned metadata must never contain a credential: the base URL is
        reported through :func:`~claimtrace_api.llm.models.safe_base_url`.
        """

    async def check_health(self) -> HealthStatus:
        """Report reachability and model availability.

        Must not raise for an unavailable provider - being down is a result, not
        an exception, and the status endpoint has to render it. Reserve raising
        for genuine programming errors.
        """

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate plain text.

        Raises:
            LLMError: mapped into the shared taxonomy. Never a provider-specific
                exception type and never one carrying a raw payload.
            asyncio.CancelledError: propagated untouched. Cancellation is not a
                failure of the provider and must not be converted into one.
        """

    async def generate_structured[SchemaT: BaseModel](
        self, request: GenerationRequest, output_model: type[SchemaT]
    ) -> StructuredGeneration[SchemaT]:
        """Generate JSON and validate it against ``output_model``.

        The provider constrains the model as strongly as its capabilities allow,
        extracts exactly one JSON value from the reply, and validates it. It
        never coerces a non-conforming answer into a conforming one, and it never
        returns a partially populated model.

        Raises:
            LLMUnsupportedCapabilityError: this provider cannot produce
                structured output safely.
            LLMMalformedJSONError: the reply was not one complete JSON value.
            LLMStructuredValidationError: the JSON did not satisfy the schema.
            LLMError: any other mapped provider failure.
        """

    async def aclose(self) -> None:
        """Release transport resources.

        Called during application shutdown. Must be safe to call more than once,
        and safe to call on a provider that never opened a connection.
        """
