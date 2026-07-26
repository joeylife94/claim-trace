"""Retry policy and URL validation.

No test here sleeps. ``run_with_retry`` takes its sleep function as an argument,
so the real backoff arithmetic runs while the waits are recorded instead of
spent - which is what makes it possible to assert the *shape* of the backoff
rather than just that a retry happened.
"""

from __future__ import annotations

import httpx
import pytest

from claimtrace_api.llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMContextLengthExceededError,
    LLMInvalidRequestError,
    LLMMalformedJSONError,
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMRateLimitedError,
    LLMStructuredValidationError,
    LLMTimeoutError,
)
from claimtrace_api.llm.retry import RetryPolicy, run_with_retry
from claimtrace_api.llm.transport import (
    TimeoutConfig,
    map_transport_error,
    retry_after_seconds,
    validate_base_url,
)


class RecordingSleep:
    """Captures the delays that would have been waited."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def failing(error: Exception, *, succeed_on: int | None = None):
    """An operation that raises until ``succeed_on``, then returns that attempt."""

    async def operation(attempt: int) -> int:
        if succeed_on is not None and attempt >= succeed_on:
            return attempt
        raise error

    return operation


# --------------------------------------------------------------------------
# Which failures are retried
# --------------------------------------------------------------------------


async def test_a_connect_failure_is_retried():
    sleep = RecordingSleep()
    result = await run_with_retry(
        failing(LLMConnectionError("refused"), succeed_on=2),
        policy=RetryPolicy(max_attempts=3),
        sleep=sleep,
    )

    assert result == 2
    assert len(sleep.delays) == 1


async def test_a_provider_unavailable_response_is_retried():
    sleep = RecordingSleep()
    result = await run_with_retry(
        failing(LLMProviderUnavailableError("loading", status=503), succeed_on=2),
        policy=RetryPolicy(max_attempts=3),
        sleep=sleep,
    )

    assert result == 2


async def test_rate_limiting_is_retried():
    sleep = RecordingSleep()
    await run_with_retry(
        failing(LLMRateLimitedError("slow down", status=429), succeed_on=2),
        policy=RetryPolicy(max_attempts=2),
        sleep=sleep,
    )

    assert len(sleep.delays) == 1


@pytest.mark.parametrize(
    "error",
    [
        LLMAuthenticationError("bad key", status=401),
        LLMInvalidRequestError("bad request", status=400),
        LLMModelNotFoundError("no model", status=404),
        LLMContextLengthExceededError("too long"),
        LLMMalformedJSONError("not json"),
        LLMStructuredValidationError("wrong shape"),
        LLMTimeoutError("read timeout"),
    ],
)
async def test_non_retryable_failures_are_raised_on_the_first_attempt(error: Exception):
    sleep = RecordingSleep()
    attempts = 0

    async def operation(attempt: int) -> int:
        nonlocal attempts
        attempts = attempt
        raise error

    with pytest.raises(type(error)):
        await run_with_retry(operation, policy=RetryPolicy(max_attempts=5), sleep=sleep)

    assert attempts == 1
    assert sleep.delays == []


async def test_a_read_timeout_is_not_retried_by_default():
    """Generation may already be running; a replay doubles the load."""
    assert LLMTimeoutError("t").retryable is False


# --------------------------------------------------------------------------
# Backoff shape and bounds
# --------------------------------------------------------------------------


async def test_max_attempts_is_honoured_and_the_last_error_is_raised():
    sleep = RecordingSleep()

    with pytest.raises(LLMConnectionError):
        await run_with_retry(
            failing(LLMConnectionError("refused")),
            policy=RetryPolicy(max_attempts=3),
            sleep=sleep,
        )

    # Three attempts means two waits between them.
    assert len(sleep.delays) == 2


async def test_backoff_grows_exponentially_and_is_capped():
    sleep = RecordingSleep()
    policy = RetryPolicy(
        max_attempts=5,
        initial_backoff_seconds=0.1,
        backoff_multiplier=2.0,
        max_backoff_seconds=0.3,
        max_total_delay_seconds=10.0,
    )

    with pytest.raises(LLMConnectionError):
        await run_with_retry(failing(LLMConnectionError("refused")), policy=policy, sleep=sleep)

    assert sleep.delays == [0.1, 0.2, 0.3, 0.3]


async def test_total_delay_is_bounded_even_with_attempts_remaining():
    sleep = RecordingSleep()
    policy = RetryPolicy(
        max_attempts=10,
        initial_backoff_seconds=0.2,
        backoff_multiplier=1.0,
        max_backoff_seconds=1.0,
        max_total_delay_seconds=0.5,
    )

    with pytest.raises(LLMConnectionError):
        await run_with_retry(failing(LLMConnectionError("refused")), policy=policy, sleep=sleep)

    assert sum(sleep.delays) <= 0.5
    assert len(sleep.delays) < 9


async def test_retry_after_overrides_the_computed_backoff():
    sleep = RecordingSleep()
    error = LLMRateLimitedError("slow down", status=429, retry_after_seconds=2.0)

    with pytest.raises(LLMRateLimitedError):
        await run_with_retry(
            failing(error),
            policy=RetryPolicy(
                max_attempts=2, initial_backoff_seconds=0.1, max_backoff_seconds=5.0
            ),
            sleep=sleep,
        )

    assert sleep.delays == [2.0]


async def test_retry_after_is_still_clamped_to_the_maximum_backoff():
    """An upstream may not hold a request open for as long as it likes."""
    sleep = RecordingSleep()
    error = LLMRateLimitedError("slow down", retry_after_seconds=600.0)

    with pytest.raises(LLMRateLimitedError):
        await run_with_retry(
            failing(error),
            policy=RetryPolicy(max_attempts=2, max_backoff_seconds=4.0),
            sleep=sleep,
        )

    assert sleep.delays == [4.0]


def test_a_policy_must_allow_at_least_one_attempt():
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)


def test_default_policy_is_conservative():
    """Two attempts, not five: a local server that is down should fail fast."""
    assert RetryPolicy().max_attempts == 2


# --------------------------------------------------------------------------
# Retry-After parsing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ({"retry-after": "3"}, 3.0),
        ({"retry-after": " 1.5 "}, 1.5),
        ({"retry-after": "0"}, 0.0),
        ({"retry-after": "-5"}, None),
        # The HTTP-date form is legal but unused by both target servers.
        ({"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}, None),
        ({}, None),
    ],
)
def test_retry_after_header_parsing(header: dict[str, str], expected: float | None):
    response = httpx.Response(429, headers=header)
    assert retry_after_seconds(response) == expected


# --------------------------------------------------------------------------
# Transport error mapping
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected_type", "retryable"),
    [
        # Never delivered, so a replay is free of side effects.
        (httpx.ConnectError("refused"), LLMConnectionError, True),
        (httpx.ConnectTimeout("timed out"), LLMConnectionError, True),
        (httpx.PoolTimeout("no connection"), LLMConnectionError, True),
        # May already be generating: not replayed.
        (httpx.ReadTimeout("slow"), LLMTimeoutError, False),
        (httpx.WriteTimeout("slow"), LLMTimeoutError, False),
    ],
)
def test_transport_errors_map_by_whether_the_request_was_delivered(
    exc: Exception, expected_type: type, retryable: bool
):
    error = map_transport_error(exc, provider="ollama", model="m")

    assert isinstance(error, expected_type)
    assert error.retryable is retryable
    assert error.provider == "ollama"


def test_transport_error_messages_do_not_quote_the_original():
    """An httpx error string can contain the full URL, and a URL can contain a key."""
    exc = httpx.ConnectError("connection to http://user:secret@host:11434 failed")
    error = map_transport_error(exc, provider="ollama", model="m")

    assert "secret" not in error.message
    assert "11434" not in error.message


# --------------------------------------------------------------------------
# Base URL validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://host.docker.internal:11434",
        "http://ollama:11434",
        "http://192.168.1.10:8000/v1",
        "https://vllm.example.com/v1",
    ],
)
def test_accepted_base_urls(url: str):
    assert validate_base_url(url, setting_name="X") == url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "ftp://host/path",
        "file:///etc/passwd",
        "not-a-url",
        "http://",
        # Plaintext to a routable host would put a credential on the wire.
        "http://api.example.com/v1",
    ],
)
def test_rejected_base_urls(url: str):
    with pytest.raises(LLMConfigurationError):
        validate_base_url(url, setting_name="LLM_TEST_BASE_URL")


def test_rejection_names_the_setting_rather_than_quoting_the_url():
    with pytest.raises(LLMConfigurationError) as exc_info:
        validate_base_url("http://user:secret@api.example.com", setting_name="LLM_X_URL")

    assert "LLM_X_URL" in exc_info.value.message
    assert "secret" not in exc_info.value.message


def test_trailing_slash_is_normalised():
    assert validate_base_url("http://localhost:11434/", setting_name="X") == (
        "http://localhost:11434"
    )


# --------------------------------------------------------------------------
# Timeout configuration
# --------------------------------------------------------------------------


def test_a_request_may_lower_the_overall_timeout():
    timeouts = TimeoutConfig(connect_seconds=5, read_seconds=120, overall_seconds=180)
    assert timeouts.bounded_by(30).overall_seconds == 30


def test_a_request_may_not_raise_the_overall_timeout():
    """The configured ceiling is the operator's decision, not the caller's."""
    timeouts = TimeoutConfig(connect_seconds=5, read_seconds=120, overall_seconds=180)
    assert timeouts.bounded_by(9999).overall_seconds == 180


def test_lowering_the_overall_timeout_also_lowers_the_read_timeout():
    """Otherwise the read would outlive the deadline it is supposed to respect."""
    timeouts = TimeoutConfig(connect_seconds=5, read_seconds=120, overall_seconds=180)
    assert timeouts.bounded_by(10).read_seconds == 10


def test_no_request_timeout_leaves_configuration_untouched():
    timeouts = TimeoutConfig(connect_seconds=5, read_seconds=120, overall_seconds=180)
    assert timeouts.bounded_by(None) == timeouts
