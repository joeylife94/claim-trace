"""Builds the one configured provider.

A factory function, not a plugin system. Three providers are supported, the
selection is a ``Literal`` on :class:`~claimtrace_api.core.config.Settings`, and
the branch that is not taken is never constructed - so a deployment running the
fake provider never validates an Ollama URL it does not use, and one running
Ollama never needs an OpenAI-compatible base URL to be set at all.

Construction opens no socket. That matters at startup: the application must come
up, serve ``/health``, and report the LLM as unreachable, rather than refusing to
start because a model server is down.
"""

from __future__ import annotations

from claimtrace_api.core.config import Settings
from claimtrace_api.llm.base import LLMProvider
from claimtrace_api.llm.errors import LLMConfigurationError
from claimtrace_api.llm.fake import FakeLLMProvider
from claimtrace_api.llm.models import StructuredOutputMode
from claimtrace_api.llm.retry import RetryPolicy
from claimtrace_api.llm.transport import TimeoutConfig


def build_timeouts(settings: Settings) -> TimeoutConfig:
    return TimeoutConfig(
        connect_seconds=settings.llm_connect_timeout_seconds,
        read_seconds=settings.llm_read_timeout_seconds,
        overall_seconds=settings.llm_max_timeout_seconds,
    )


def build_retry_policy(settings: Settings) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=settings.llm_retry_max_attempts,
        initial_backoff_seconds=settings.llm_retry_initial_backoff_seconds,
        max_backoff_seconds=settings.llm_retry_max_backoff_seconds,
        max_total_delay_seconds=settings.llm_retry_max_total_delay_seconds,
    )


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Construct the provider named by ``LLM_PROVIDER``.

    Raises:
        LLMConfigurationError: the selected provider is missing a setting it
            cannot run without, or its base URL is not usable. Raised eagerly,
            with the name of the setting to fix.
    """
    timeouts = build_timeouts(settings)
    retry_policy = build_retry_policy(settings)

    match settings.llm_provider:
        case "fake":
            return FakeLLMProvider()

        case "ollama":
            if not settings.llm_ollama_model.strip():
                raise LLMConfigurationError("LLM_OLLAMA_MODEL must be set.")
            # Imported inside the branch, matching how the embedding provider
            # defers its heavy import: an installation on the fake provider
            # should not need the adapter's dependencies resolved at all.
            from claimtrace_api.llm.ollama import OllamaProvider

            return OllamaProvider(
                base_url=settings.llm_ollama_base_url,
                model=settings.llm_ollama_model,
                timeouts=timeouts,
                retry_policy=retry_policy,
            )

        case "openai_compatible":
            if not settings.llm_openai_compatible_model.strip():
                raise LLMConfigurationError("LLM_OPENAI_COMPATIBLE_MODEL must be set.")
            from claimtrace_api.llm.openai_compatible import OpenAICompatibleProvider

            return OpenAICompatibleProvider(
                base_url=settings.llm_openai_compatible_base_url,
                model=settings.llm_openai_compatible_model,
                api_key=settings.llm_openai_compatible_api_key,
                structured_output_mode=StructuredOutputMode(settings.llm_structured_output_mode),
                timeouts=timeouts,
                retry_policy=retry_policy,
            )

    # Unreachable while the setting is a Literal, and kept anyway: the failure
    # mode it guards against is someone widening that Literal without widening
    # this match, and a clear error beats an implicit None.
    raise LLMConfigurationError(  # pragma: no cover - guarded by the Literal
        f"Unknown LLM provider: {settings.llm_provider!r}"
    )
