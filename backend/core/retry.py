"""RetryPolicy — jittered exponential backoff for LLM HTTP calls.

Retries on transient failures (429, 503, network errors) up to max_retries
times, bounded by a monotonic deadline.  Non-retryable status codes (400, 401)
are propagated immediately.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Awaitable, Callable, TypeVar

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class LLMUnavailableError(Exception):
    """Raised when an LLM endpoint is unavailable after all retry attempts."""


class RetryPolicy:
    """Jittered exponential backoff retry policy for async callables.

    Args:
        max_retries:  Maximum number of retry attempts (not counting the
                      initial call).  Defaults to ``settings.LLM_RETRY_MAX``.
        base_delay:   Base delay in seconds for the backoff formula.
                      Defaults to ``settings.LLM_RETRY_BASE_DELAY``.
        max_delay:    Upper cap on the computed delay (before jitter).
                      Defaults to ``settings.LLM_RETRY_MAX_DELAY``.
    """

    retryable_status_codes: frozenset[int] = frozenset({429, 503})
    non_retryable_status_codes: frozenset[int] = frozenset({400, 401})

    def __init__(
        self,
        max_retries: int | None = None,
        base_delay: float | None = None,
        max_delay: float | None = None,
    ) -> None:
        self.max_retries = max_retries if max_retries is not None else settings.LLM_RETRY_MAX
        self.base_delay = base_delay if base_delay is not None else settings.LLM_RETRY_BASE_DELAY
        self.max_delay = max_delay if max_delay is not None else settings.LLM_RETRY_MAX_DELAY

    # ------------------------------------------------------------------
    # Delay calculation (pure, easily testable)
    # ------------------------------------------------------------------

    def compute_delay(self, attempt: int) -> float:
        """Return ``min(base_delay * 2^attempt, max_delay) + uniform(0, 1)``."""
        base = min(self.base_delay * (2 ** attempt), self.max_delay)
        return base + random.uniform(0, 1)

    # ------------------------------------------------------------------
    # Core execute method
    # ------------------------------------------------------------------

    async def execute(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        deadline: float,
        **kwargs: Any,
    ) -> T:
        """Execute *fn* with retry logic, bounded by *deadline*.

        Args:
            fn:       Async callable to invoke.
            *args:    Positional arguments forwarded to *fn*.
            deadline: ``time.monotonic()`` value after which no further
                      attempts are made.
            **kwargs: Keyword arguments forwarded to *fn*.

        Returns:
            The return value of *fn* on success.

        Raises:
            LLMUnavailableError: When all retries are exhausted, a
                non-retryable error is encountered, or the deadline is
                exceeded.
        """
        last_exc: Exception | None = None
        endpoint_url: str = getattr(fn, "__self__", fn).__class__.__name__

        # Try to extract a meaningful endpoint URL from the callable's owner
        owner = getattr(fn, "__self__", None)
        if owner is not None and hasattr(owner, "base_url"):
            endpoint_url = owner.base_url

        for attempt in range(self.max_retries + 1):
            # Check deadline before attempting
            if time.monotonic() >= deadline:
                raise LLMUnavailableError(
                    f"LLM_TIMEOUT exceeded before attempt {attempt} "
                    f"(endpoint={endpoint_url})"
                )

            status_code: int | None = None
            exc_type: str | None = None

            try:
                result = await fn(*args, **kwargs)

                if attempt > 0:
                    logger.info(
                        "LLM call succeeded after %d retries (endpoint=%s)",
                        attempt,
                        endpoint_url,
                    )
                return result

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status_code = exc.response.status_code

                logger.debug(
                    "LLM attempt failed: attempt_number=%d endpoint_url=%s "
                    "status_code=%d",
                    attempt,
                    endpoint_url,
                    status_code,
                )

                if status_code in self.non_retryable_status_codes:
                    raise LLMUnavailableError(
                        f"Non-retryable HTTP {status_code} from {endpoint_url}"
                    ) from exc

                if status_code not in self.retryable_status_codes:
                    raise LLMUnavailableError(
                        f"Unexpected HTTP {status_code} from {endpoint_url}"
                    ) from exc

            except (httpx.RequestError, OSError, TimeoutError) as exc:
                last_exc = exc
                exc_type = type(exc).__name__
                logger.debug(
                    "LLM attempt failed: attempt_number=%d endpoint_url=%s "
                    "exception_type=%s",
                    attempt,
                    endpoint_url,
                    exc_type,
                )

            # No more retries after the last attempt
            if attempt >= self.max_retries:
                break

            # Compute delay and check deadline before sleeping
            delay = self.compute_delay(attempt)
            logger.debug(
                "LLM retry scheduled: attempt_number=%d endpoint_url=%s "
                "delay_seconds=%.3f",
                attempt,
                endpoint_url,
                delay,
            )

            # Don't sleep past the deadline
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LLMUnavailableError(
                    f"LLM_TIMEOUT exceeded before retry {attempt + 1} "
                    f"(endpoint={endpoint_url})"
                )
            await asyncio.sleep(min(delay, remaining))

        raise LLMUnavailableError(
            f"LLM call exhausted {self.max_retries} retries (endpoint={endpoint_url})"
        ) from last_exc
