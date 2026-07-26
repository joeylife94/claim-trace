"""The generation use case.

Sits between the HTTP layer and a provider and owns four things: turning loose
inputs into a validated :class:`GenerationRequest`, enforcing the configured
ceilings, translating the LLM taxonomy into the application's, and emitting the
safe operational log line.

What it deliberately does *not* do, at this phase: it never touches the
retrieval service, never queries a claim, never assembles patent context, never
produces a citation, and never persists anything. Phase 4A-1 builds the
generation infrastructure; grounding generation in retrieved evidence is Phase
4A-2, and keeping this class empty of retrieval is what makes that a new
collaborator rather than a rewrite.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from pydantic import BaseModel

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.llm.base import LLMProvider, StructuredGeneration
from claimtrace_api.llm.errors import LLMError
from claimtrace_api.llm.models import (
    GenerationOptions,
    GenerationRequest,
    GenerationResponse,
    HealthStatus,
    Message,
    MessageRole,
    ProviderMetadata,
)

logger = logging.getLogger(__name__)


class LLMGenerationService:
    """Validates, bounds, and executes one generation against the configured provider."""

    def __init__(self, *, provider: LLMProvider, settings: Settings) -> None:
        self._provider = provider
        self._settings = settings

    # -- diagnostics --------------------------------------------------------

    def get_metadata(self) -> ProviderMetadata:
        """Describe the provider without contacting it."""
        return self._provider.get_metadata()

    async def check_health(self) -> HealthStatus:
        """Probe the provider.

        Translates an unexpected provider exception into an unavailable status
        rather than letting it escape: the status endpoint's job is to report
        that the LLM is down, and a status endpoint that 500s when the thing it
        reports on is down is not doing that job.
        """
        try:
            return await self._provider.check_health()
        except LLMError as error:
            logger.info("llm health check failed", extra=error.log_fields())
            return HealthStatus(
                available=False,
                model_available=False,
                detail=error.message,
                error_code=error.code.value,
            )

    # -- generation ---------------------------------------------------------

    async def generate_text(
        self,
        *,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> GenerationResponse:
        """Generate plain text.

        Raises:
            AppError: every provider failure, mapped to a client-safe code.
        """
        request = self._build_request(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        async with self._mapped_errors(request, structured=False):
            return await self._provider.generate(request)

    async def generate_structured[SchemaT: BaseModel](
        self,
        *,
        prompt: str,
        output_model: type[SchemaT],
        system: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> StructuredGeneration[SchemaT]:
        """Generate JSON validated against ``output_model``.

        ``output_model`` is a Python type chosen by the caller, never a schema
        received over HTTP. The diagnostics endpoint passes one fixed model; an
        internal caller may pass any approved Pydantic model.

        Raises:
            AppError: every provider failure, mapped to a client-safe code.
        """
        request = self._build_request(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        async with self._mapped_errors(request, structured=True):
            return await self._provider.generate_structured(request, output_model)

    # -- internals ----------------------------------------------------------

    def _build_request(
        self,
        *,
        prompt: str,
        system: str | None,
        temperature: float | None,
        max_output_tokens: int | None,
        timeout_seconds: float | None,
    ) -> GenerationRequest:
        """Assemble and bound a request.

        Bounds are applied in two different ways on purpose. An oversized prompt
        is *rejected*, because silently truncating patent text would change the
        question being asked. An oversized token limit or timeout is *clamped*,
        because those only describe how much room the answer is given, and the
        configured maximum is the operator's decision to enforce rather than the
        caller's to be lectured about.
        """
        text = prompt.strip()
        if not text:
            raise AppError(ErrorCode.LLM_INVALID_REQUEST, "The prompt may not be empty.")

        limit = self._settings.llm_max_prompt_characters
        total = len(text) + len(system or "")
        if total > limit:
            raise AppError(
                ErrorCode.LLM_INVALID_REQUEST,
                f"The prompt is {total} characters; the limit is {limit}.",
            )

        messages: list[Message] = []
        if system and system.strip():
            messages.append(Message(role=MessageRole.SYSTEM, content=system.strip()))
        messages.append(Message(role=MessageRole.USER, content=text))

        # Both constructions are guarded, not just the request: GenerationOptions
        # validates its own bounds, so an out-of-range temperature raises here
        # too. Leaving it uncaught would let an LLMError escape the service
        # unmapped and surface as a 500 instead of the 400 it is.
        try:
            options = GenerationOptions(
                temperature=temperature,
                max_output_tokens=(
                    min(max_output_tokens, self._settings.llm_max_output_tokens)
                    if max_output_tokens is not None
                    else None
                ),
                timeout_seconds=(
                    min(timeout_seconds, self._settings.llm_max_timeout_seconds)
                    if timeout_seconds is not None
                    else None
                ),
            )
            return GenerationRequest(
                messages=tuple(messages),
                options=options,
                # Random rather than derived from the prompt: correlation needs
                # only uniqueness, and a content-derived id would be a weak
                # fingerprint of confidential text sitting in every log line.
                request_id=uuid.uuid4().hex[:12],
            )
        except LLMError as error:
            raise self._to_app_error(error) from error

    def _mapped_errors(self, request: GenerationRequest, *, structured: bool) -> _MappedErrors:
        return _MappedErrors(request=request, structured=structured)

    @staticmethod
    def _to_app_error(error: LLMError) -> AppError:
        """Translate the LLM taxonomy into the application's.

        A one-to-one code mapping: every ``LLMErrorCode`` has an ``ErrorCode`` of
        the same value, which a test enforces. The message is already
        client-safe by construction - the adapters never build one out of a
        provider payload.
        """
        return AppError(ErrorCode(error.code.value), error.message)


class _MappedErrors:
    """Async context manager translating provider failures at one place.

    Written as a class rather than an ``asynccontextmanager`` because the latter
    cannot re-raise a different exception type from ``__aexit__`` without
    confusing the traceback, and because cancellation has to pass through
    untouched - which is easier to see, and to test, when it is one explicit
    branch.
    """

    def __init__(self, *, request: GenerationRequest, structured: bool) -> None:
        self._request = request
        self._structured = structured

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        if exc is None:
            return False

        context = {**self._request.log_fields(), "structured": self._structured}

        if isinstance(exc, asyncio.CancelledError):
            # Re-raised unchanged by returning False. Turning a cancellation into
            # a 500 would report a client that disconnected as a server fault,
            # and would stop the cancellation from unwinding the task group.
            logger.info("llm generation cancelled", extra=context)
            return False

        if isinstance(exc, LLMError):
            # An expected failure: logged at info with the safe fields and no
            # traceback. A stack trace for "the model server is not running" is
            # noise that trains an operator to ignore stack traces.
            logger.info("llm generation failed", extra={**context, **exc.log_fields()})
            raise LLMGenerationService._to_app_error(exc) from exc

        return False
