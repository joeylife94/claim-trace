"""A conservative retry policy for provider calls.

The default is two attempts, not five. A local model server is not a flaky cloud
API: when it refuses a connection the usual cause is that it is not running, and
hammering it four more times converts a fast, clear failure into a slow, clear
failure. Retrying earns its place for exactly one situation - the request never
reached the server, or the server explicitly said "later".

What is never retried automatically:

* **Read timeouts.** By the time a read times out the server may already be
  generating. A replay doubles the load on a machine that has just demonstrated
  it is too slow, and on a single-GPU box that makes the timeout self-fulfilling.
* **Authentication, invalid request, model-not-found, context length.** Fixed by
  changing something, never by asking again.
* **Malformed JSON and schema validation failures.** A resample might produce
  valid output, but silently burning tokens until the model happens to comply
  hides a genuine mismatch between the schema and the model's ability. The
  failure is reported instead.

Whether a failure is retryable is decided by the adapter that mapped it, and
travels on :attr:`~claimtrace_api.llm.errors.LLMError.retryable`. This module
only reads that flag - it never re-inspects a status code.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from claimtrace_api.llm.errors import LLMError

logger = logging.getLogger(__name__)

#: Injectable so tests exercise the real backoff arithmetic without spending the
#: real seconds. Production always passes :func:`asyncio.sleep`.
SleepFn = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How many times, and how long to wait between attempts.

    ``max_attempts`` counts the first try, so ``2`` means "one retry".
    """

    max_attempts: int = 2
    initial_backoff_seconds: float = 0.25
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 4.0
    #: Ceiling on the sum of all waits. Reached, it stops further attempts even
    #: when ``max_attempts`` has not been exhausted, so a generous attempt count
    #: can never turn into an unbounded wait.
    max_total_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValueError("backoff values must not be negative")

    def backoff_for(self, attempt: int, *, retry_after_seconds: float | None = None) -> float:
        """Seconds to wait before attempt ``attempt + 1``.

        ``attempt`` is 1-based. A provider-supplied ``Retry-After`` wins over the
        computed backoff - it is the server telling us when it will be ready -
        but is still clamped to :attr:`max_backoff_seconds`, because an upstream
        that asks for a five-minute wait must not be allowed to hold a request
        open for five minutes.
        """
        if retry_after_seconds is not None and retry_after_seconds >= 0:
            return min(retry_after_seconds, self.max_backoff_seconds)

        computed = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(computed, self.max_backoff_seconds)


class RetryState:
    """Mutable bookkeeping for one retried operation."""

    def __init__(self, policy: RetryPolicy) -> None:
        self.policy = policy
        self.attempt = 0
        self.total_delay = 0.0

    def should_retry(self, error: LLMError) -> bool:
        if not error.retryable:
            return False
        if self.attempt >= self.policy.max_attempts:
            return False
        return self.total_delay < self.policy.max_total_delay_seconds

    def next_delay(self, error: LLMError) -> float:
        """The next wait, clamped so the total never exceeds the budget."""
        delay = self.policy.backoff_for(self.attempt, retry_after_seconds=error.retry_after_seconds)
        remaining = self.policy.max_total_delay_seconds - self.total_delay
        return max(0.0, min(delay, remaining))


async def run_with_retry[ResultT](
    operation: Callable[[int], Awaitable[ResultT]],
    *,
    policy: RetryPolicy,
    sleep: SleepFn = asyncio.sleep,
    log_context: dict[str, object] | None = None,
) -> ResultT:
    """Run ``operation`` until it succeeds, is not retryable, or runs out of budget.

    ``operation`` receives the 1-based attempt number so an adapter can record it
    on the response it returns.

    :class:`asyncio.CancelledError` is never caught here. Cancellation means the
    caller has gone away, and retrying on its behalf would be both wasteful and
    wrong; letting it propagate is what makes cancellation prompt.

    Raises:
        LLMError: the last error seen, once no further attempt is permitted.
    """
    state = RetryState(policy)
    context = log_context or {}

    while True:
        state.attempt += 1
        try:
            return await operation(state.attempt)
        except LLMError as error:
            if not state.should_retry(error):
                # Logged at the point the decision is made, so a non-retryable
                # failure on attempt 1 is distinguishable from an exhausted one.
                logger.info(
                    "llm attempt failed, not retrying",
                    extra={
                        **context,
                        **error.log_fields(),
                        "attempt": state.attempt,
                        "max_attempts": policy.max_attempts,
                    },
                )
                raise

            delay = state.next_delay(error)
            state.total_delay += delay
            logger.warning(
                "llm attempt failed, retrying",
                extra={
                    **context,
                    **error.log_fields(),
                    "attempt": state.attempt,
                    "max_attempts": policy.max_attempts,
                    "retry_delay_seconds": round(delay, 3),
                },
            )
            if delay > 0:
                await sleep(delay)
