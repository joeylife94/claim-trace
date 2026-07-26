"""Shared HTTP concerns for the network-backed providers.

Both adapters speak plain JSON over HTTP to a server on the local network, so
neither needs a vendor SDK. ``httpx`` alone is enough, and choosing it over the
``openai`` package is deliberate: the SDK would pull its own retry loop, its own
timeout model, and its own exception hierarchy into a boundary whose entire
purpose is to present *one* of each. A hundred lines of adapter is a better trade
than a dependency that has to be talked out of doing its job.

This module owns three things the adapters would otherwise each get subtly
wrong: what a base URL is allowed to be, how a timeout is split, and which
transport failure maps to which taxonomy entry.
"""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

import httpx

from claimtrace_api.llm.errors import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMError,
    LLMTimeoutError,
)
from claimtrace_api.llm.retry import RetryPolicy, run_with_retry

#: Hosts allowed to be reached over plaintext HTTP. Everything else must use
#: HTTPS, so a credential cannot be sent in the clear to a routable address.
_LOCAL_HOSTNAMES = frozenset({"localhost", "host.docker.internal"})


@dataclass(frozen=True, slots=True)
class TimeoutConfig:
    """The three deadlines a generation call is bounded by.

    They are separate because they mean different things and are tuned against
    different failures. ``connect`` catches "nothing is listening" in a second or
    two. ``read`` bounds a single quiet stretch. ``overall`` bounds the whole
    operation including retries, and is the one a caller may lower per request.

    A CPU-hosted model answers slowly, so ``read`` is generous by default while
    ``connect`` stays short: a wrong port should fail immediately, a working
    model should be given time to think.
    """

    connect_seconds: float = 5.0
    read_seconds: float = 120.0
    overall_seconds: float = 180.0

    def bounded_by(self, requested_seconds: float | None) -> TimeoutConfig:
        """Apply a per-request overall timeout.

        A request may only ever *lower* the ceiling. Anything larger is clamped
        rather than rejected, because the configured maximum is the operator's
        decision and a caller does not get to raise it.
        """
        if requested_seconds is None:
            return self
        overall = min(requested_seconds, self.overall_seconds)
        # A short overall deadline makes a long read timeout meaningless; keeping
        # them consistent means the read fails at the deadline rather than after
        # it, and the error says "timeout" instead of hanging until the outer
        # cancellation fires.
        return replace(self, overall_seconds=overall, read_seconds=min(self.read_seconds, overall))

    def to_httpx(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_seconds,
            read=self.read_seconds,
            write=self.connect_seconds,
            pool=self.connect_seconds,
        )


def validate_base_url(url: str, *, setting_name: str) -> str:
    """Check a provider base URL and return it without a trailing slash.

    Provider URLs come only from server configuration - never from a request
    body, a query parameter, or a header - so this is a guard against operator
    error rather than an SSRF defence. It enforces three things:

    * the scheme is ``http`` or ``https`` and nothing else;
    * a host is present;
    * plaintext ``http`` is used only for a local address.

    Raises:
        LLMConfigurationError: naming the setting, so the message is actionable
            without quoting a URL that might carry a credential.
    """
    parts = urlsplit(url)

    if parts.scheme not in ("http", "https"):
        raise LLMConfigurationError(f"{setting_name} must use http or https.")
    if not parts.hostname:
        raise LLMConfigurationError(f"{setting_name} must include a host.")

    if parts.scheme == "http" and not _is_local_host(parts.hostname):
        raise LLMConfigurationError(
            f"{setting_name} must use https for a non-local host. Plaintext http "
            "is permitted only for localhost, a private address, or a container "
            "service name."
        )

    return url.rstrip("/")


def _is_local_host(hostname: str) -> bool:
    """Whether plaintext HTTP to this host stays inside the deployment."""
    host = hostname.strip("[]").lower()

    if host in _LOCAL_HOSTNAMES or host.endswith(".localhost"):
        return True

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Not an IP literal. A single-label name is a Docker Compose service
        # ("ollama", "api") and resolves only on the container network; a dotted
        # name is a real DNS name and must use TLS.
        return "." not in host

    return address.is_loopback or address.is_private or address.is_link_local


def map_transport_error(exc: Exception, *, provider: str, model: str | None) -> LLMError:
    """Translate an ``httpx`` transport failure into the shared taxonomy.

    The retryable split follows one rule: was the request delivered? A connect
    failure, a connect timeout, and a pool timeout all mean it was not, so a
    replay is free of side effects and is allowed. A read timeout means the
    server may already be generating, so it is not retried - see
    :mod:`claimtrace_api.llm.retry` for why that matters on a single-GPU host.

    The original exception is never rendered into the message: an httpx error
    string can contain the full URL, and a URL can contain a credential.
    """
    if isinstance(exc, httpx.ConnectTimeout | httpx.PoolTimeout):
        return LLMConnectionError(
            "Timed out establishing a connection to the model provider.",
            provider=provider,
            model=model,
        )
    if isinstance(exc, httpx.ConnectError):
        return LLMConnectionError(
            "Could not connect to the model provider.", provider=provider, model=model
        )
    if isinstance(exc, httpx.TimeoutException):
        return LLMTimeoutError(
            "The model provider did not respond before the timeout.",
            provider=provider,
            model=model,
        )
    return LLMConnectionError(
        "The connection to the model provider failed.", provider=provider, model=model
    )


async def run_bounded[ResultT](
    operation: Callable[[int], Awaitable[ResultT]],
    *,
    timeouts: TimeoutConfig,
    policy: RetryPolicy,
    provider: str,
    model: str | None,
    log_context: dict[str, object] | None = None,
) -> tuple[ResultT, int]:
    """Run ``operation`` under one overall deadline, retrying where permitted.

    The deadline wraps the *retry loop*, not each attempt, so a configured
    ceiling of 180s means the caller waits at most 180s in total however many
    attempts and backoffs fit inside it.

    Returns the result together with the attempt number that produced it, which
    the adapters record on the response.

    :class:`asyncio.CancelledError` from outside is never caught:
    :func:`asyncio.timeout` re-raises :class:`TimeoutError` only when it was the
    one that cancelled the body, so an external cancellation passes straight
    through and stays a cancellation.

    Raises:
        LLMTimeoutError: the overall deadline expired.
        LLMError: the last failure, when no further attempt is permitted.
    """
    attempts = 0

    async def counted(attempt_number: int) -> ResultT:
        nonlocal attempts
        attempts = attempt_number
        return await operation(attempt_number)

    try:
        async with asyncio.timeout(timeouts.overall_seconds):
            result = await run_with_retry(counted, policy=policy, log_context=log_context)
    except TimeoutError as exc:
        raise LLMTimeoutError(
            f"Generation exceeded the {timeouts.overall_seconds:g}s timeout.",
            provider=provider,
            model=model,
        ) from exc

    return result, attempts


def retry_after_seconds(response: httpx.Response) -> float | None:
    """Read a ``Retry-After`` header expressed in seconds.

    Only the delta-seconds form is honoured. The HTTP-date form is legal but is
    not emitted by either target server, and parsing a date against a possibly
    skewed clock to decide a sub-second backoff is not worth the failure mode.
    """
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    return value if value >= 0 else None
