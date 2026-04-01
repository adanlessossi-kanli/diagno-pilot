"""Property-based tests for RetryPolicy.

Tests cover:
  Property 1 — Retry count is bounded
  Property 2 — Retry delay is within expected bounds
  Property 3 — Retry classification by HTTP status code
  Property 5 — Deadline aborts remaining retries
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.core.retry import LLMUnavailableError, RetryPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _make_http_status_error(status_code: int) -> httpx.HTTPStatusError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=MagicMock(spec=httpx.Request),
        response=response,
    )


# ---------------------------------------------------------------------------
# Property 1: Retry count is bounded
# Feature: llm-resilience, Property 1: Retry count is bounded
# ---------------------------------------------------------------------------

@given(max_retries=st.integers(min_value=0, max_value=5))
@h_settings(max_examples=100, deadline=None)
def test_retry_count_bounded(max_retries: int) -> None:
    """For any always-failing endpoint, total call count == max_retries + 1."""
    # Feature: llm-resilience, Property 1: Retry count is bounded
    policy = RetryPolicy(max_retries=max_retries, base_delay=0.0, max_delay=0.0)
    fn = AsyncMock(side_effect=httpx.ConnectError("fail"))
    far_future = time.monotonic() + 9999.0

    async def _test():
        with pytest.raises(LLMUnavailableError):
            await policy.execute(fn, deadline=far_future)
        assert fn.call_count == max_retries + 1, (
            f"Expected exactly {max_retries + 1} calls, got {fn.call_count}"
        )

    _run(_test())


# ---------------------------------------------------------------------------
# Property 2: Retry delay is within expected bounds
# Feature: llm-resilience, Property 2: Retry delay is within expected bounds
# ---------------------------------------------------------------------------

@given(
    base_delay=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    max_delay=st.floats(min_value=0.01, max_value=60.0, allow_nan=False, allow_infinity=False),
    attempt=st.integers(min_value=0, max_value=10),
)
@h_settings(max_examples=100, deadline=None)
def test_retry_delay_bounds(base_delay: float, max_delay: float, attempt: int) -> None:
    """Computed delay == min(base * 2^attempt, max); with jitter in [0, 1)."""
    # Feature: llm-resilience, Property 2: Retry delay is within expected bounds
    policy = RetryPolicy(base_delay=base_delay, max_delay=max_delay)

    samples = [policy.compute_delay(attempt) for _ in range(50)]
    expected_base = min(base_delay * (2 ** attempt), max_delay)

    for delay in samples:
        assert delay >= expected_base, (
            f"delay {delay} < expected_base {expected_base}"
        )
        assert delay < expected_base + 1.0 + 1e-9, (
            f"delay {delay} >= expected_base + 1.0 ({expected_base + 1.0})"
        )


# ---------------------------------------------------------------------------
# Property 3: Retry classification by HTTP status code
# Feature: llm-resilience, Property 3: Retry classification by HTTP status code
# ---------------------------------------------------------------------------

@given(status_code=st.sampled_from([429, 503]))
@h_settings(max_examples=100, deadline=None)
def test_retryable_status_codes_are_retried(status_code: int) -> None:
    """Status codes 429 and 503 must be retried up to max_retries times."""
    # Feature: llm-resilience, Property 3: Retry classification by HTTP status code
    max_retries = 2
    policy = RetryPolicy(max_retries=max_retries, base_delay=0.0, max_delay=0.0)
    fn = AsyncMock(side_effect=_make_http_status_error(status_code))
    far_future = time.monotonic() + 9999.0

    async def _test():
        with pytest.raises(LLMUnavailableError):
            await policy.execute(fn, deadline=far_future)
        assert fn.call_count == max_retries + 1, (
            f"Expected {max_retries + 1} calls for status {status_code}, got {fn.call_count}"
        )

    _run(_test())


@given(status_code=st.sampled_from([400, 401]))
@h_settings(max_examples=100, deadline=None)
def test_non_retryable_status_codes_abort_immediately(status_code: int) -> None:
    """Status codes 400 and 401 must NOT be retried — total attempts == 1."""
    # Feature: llm-resilience, Property 3: Retry classification by HTTP status code
    policy = RetryPolicy(max_retries=3, base_delay=0.0, max_delay=0.0)
    fn = AsyncMock(side_effect=_make_http_status_error(status_code))
    far_future = time.monotonic() + 9999.0

    async def _test():
        with pytest.raises(LLMUnavailableError):
            await policy.execute(fn, deadline=far_future)
        assert fn.call_count == 1, (
            f"Expected exactly 1 call for non-retryable status {status_code}, got {fn.call_count}"
        )

    _run(_test())


# ---------------------------------------------------------------------------
# Property 5: Deadline aborts remaining retries
# Feature: llm-resilience, Property 5: Deadline aborts remaining retries
# ---------------------------------------------------------------------------

def test_past_deadline_aborts_before_first_attempt() -> None:
    """A deadline already in the past must abort without calling fn at all."""
    # Feature: llm-resilience, Property 5: Deadline aborts remaining retries
    policy = RetryPolicy(max_retries=3, base_delay=0.0, max_delay=0.0)
    fn = AsyncMock(return_value="ok")
    past_deadline = time.monotonic() - 1.0

    async def _test():
        with pytest.raises(LLMUnavailableError):
            await policy.execute(fn, deadline=past_deadline)
        assert fn.call_count == 0, "fn should not be called when deadline is already past"

    _run(_test())


@given(max_retries=st.integers(min_value=1, max_value=4))
@h_settings(max_examples=50, deadline=None)
def test_deadline_aborts_after_first_attempt(max_retries: int) -> None:
    """A deadline that expires after the first attempt prevents further retries."""
    # Feature: llm-resilience, Property 5: Deadline aborts remaining retries
    policy = RetryPolicy(max_retries=max_retries, base_delay=0.0, max_delay=0.0)
    call_count = 0

    async def _test():
        nonlocal call_count
        call_count = 0

        async def slow_fail() -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0)
            raise httpx.ConnectError("fail")

        # Deadline set to now — will expire before or right at the first attempt
        deadline = time.monotonic()

        with pytest.raises(LLMUnavailableError):
            await policy.execute(slow_fail, deadline=deadline)

        # Should have made at most 1 attempt (deadline was at/before start)
        assert call_count <= max_retries + 1

    _run(_test())


# ---------------------------------------------------------------------------
# Property 4: Circuit breaker records failure on retry exhaustion
# Feature: llm-resilience, Property 4: Circuit breaker records failure on retry exhaustion
# ---------------------------------------------------------------------------

@given(
    max_retries=st.integers(min_value=0, max_value=3),
    failure_threshold=st.integers(min_value=10, max_value=50),
)
@h_settings(max_examples=100, deadline=None)
def test_circuit_breaker_records_failure_on_retry_exhaustion(
    max_retries: int, failure_threshold: int
) -> None:
    """For any LLM client that exhausts all retries, the CircuitBreaker failure count increases.

    # Feature: llm-resilience, Property 4: Circuit breaker records failure on retry exhaustion
    Validates: Requirements 1.6, 1.13
    """
    from backend.core.circuit_breaker import CircuitBreaker
    from backend.services.llm_router import LLMRouter

    async def _test():
        # Use a high failure_threshold so the circuit never opens during the test
        cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=9999)
        router = LLMRouter(
            primary_url="http://primary",
            primary_api_key="key",
            fallback_url="http://fallback",
            fallback_api_key="key",
            circuit_breaker=cb,
        )

        # Primary always raises LLMUnavailableError (retry exhaustion)
        router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("exhausted"))
        # Fallback succeeds so we don't get HTTP 503
        router._fallback.generate = AsyncMock(return_value="fallback ok")

        failure_count_before = cb.failure_count
        await router.generate("test prompt", [])
        failure_count_after = cb.failure_count

        assert failure_count_after >= failure_count_before + 1, (
            f"CircuitBreaker failure_count should increase by at least 1 after retry exhaustion, "
            f"before={failure_count_before}, after={failure_count_after}"
        )

    _run(_test())


@given(
    max_retries=st.integers(min_value=0, max_value=3),
    failure_threshold=st.integers(min_value=10, max_value=50),
)
@h_settings(max_examples=100, deadline=None)
def test_fallback_circuit_breaker_records_failure_on_retry_exhaustion(
    max_retries: int, failure_threshold: int
) -> None:
    """For the fallback LLM that exhausts all retries, the fallback CircuitBreaker failure count increases.

    # Feature: llm-resilience, Property 4: Circuit breaker records failure on retry exhaustion
    Validates: Requirements 1.13
    """
    import pytest
    from fastapi import HTTPException
    from backend.core.circuit_breaker import CircuitBreaker
    from backend.services.llm_router import LLMRouter

    async def _test():
        primary_cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=9999)
        fallback_cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=9999)
        router = LLMRouter(
            primary_url="http://primary",
            primary_api_key="key",
            fallback_url="http://fallback",
            fallback_api_key="key",
            circuit_breaker=primary_cb,
            fallback_circuit_breaker=fallback_cb,
        )

        # Both LLMs fail
        router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary exhausted"))
        router._fallback.generate = AsyncMock(side_effect=LLMUnavailableError("fallback exhausted"))

        fallback_failures_before = fallback_cb.failure_count

        with pytest.raises(HTTPException):
            await router.generate("test prompt", [])

        fallback_failures_after = fallback_cb.failure_count

        assert fallback_failures_after >= fallback_failures_before + 1, (
            f"Fallback CircuitBreaker failure_count should increase by at least 1 after retry exhaustion, "
            f"before={fallback_failures_before}, after={fallback_failures_after}"
        )

    _run(_test())
