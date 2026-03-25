"""Circuit breaker for protecting calls to external services (LLM).

States:
  CLOSED   — normal operation, calls pass through
  OPEN     — circuit tripped, calls fail fast with CircuitOpenError
  HALF_OPEN — recovery probe, one test call allowed through
"""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum, auto
from typing import Any, Awaitable, Callable, TypeVar

from backend.core.metrics import circuit_breaker_open_total

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is OPEN."""


class CircuitBreaker:
    """Async circuit breaker with CLOSED → OPEN → HALF_OPEN state machine.

    Args:
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout:  Seconds to wait in OPEN state before probing.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 120.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def call(self, coro: Awaitable[T]) -> T:
        """Execute *coro*, applying circuit-breaker logic.

        Raises:
            CircuitOpenError: if the circuit is OPEN and the recovery
                              timeout has not yet elapsed.
        """
        async with self._lock:
            current_state = self._evaluate_state()

        if current_state == CircuitState.OPEN:
            # Close the coroutine to avoid "coroutine was never awaited" warnings
            if hasattr(coro, "close"):
                coro.close()  # type: ignore[union-attr]
            raise CircuitOpenError(
                f"Circuit is OPEN (failures={self._failure_count}). "
                "Call blocked to protect downstream service."
            )

        try:
            result = await coro
        except Exception as exc:
            async with self._lock:
                self._on_failure()
            raise
        else:
            async with self._lock:
                self._on_success()
            return result

    async def call_fn(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """Call *fn(*args, **kwargs)* with circuit-breaker protection.

        Unlike ``call()``, the coroutine is only created **after** the circuit
        state is checked, so the underlying callable is never invoked when the
        circuit is OPEN.

        Raises:
            CircuitOpenError: if the circuit is OPEN.
        """
        async with self._lock:
            current_state = self._evaluate_state()

        if current_state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit is OPEN (failures={self._failure_count}). "
                "Call blocked to protect downstream service."
            )

        try:
            result = await fn(*args, **kwargs)
        except Exception:
            async with self._lock:
                self._on_failure()
            raise
        else:
            async with self._lock:
                self._on_success()
            return result

    # ------------------------------------------------------------------
    # Internal state transitions
    # ------------------------------------------------------------------

    def _evaluate_state(self) -> CircuitState:
        """Transition OPEN → HALF_OPEN if recovery_timeout has elapsed."""
        if self._state == CircuitState.OPEN:
            assert self._opened_at is not None
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    "Circuit breaker transitioning to HALF_OPEN after recovery timeout."
                )
        return self._state

    def _on_failure(self) -> None:
        """Record a failure; open the circuit if threshold is reached."""
        if self._state == CircuitState.HALF_OPEN:
            # Probe failed — go back to OPEN
            self._trip()
            return

        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._trip()

    def _on_success(self) -> None:
        """Record a success; reset the circuit if it was HALF_OPEN."""
        if self._state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker closing after successful probe.")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None

    def _trip(self) -> None:
        """Open the circuit and log a WARNING."""
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        logger.warning(
            "Circuit breaker OPENED — failure_count=%d, opened_at=%s",
            self._failure_count,
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
        )
        # Increment Prometheus counter (REQ 18.4)
        try:
            circuit_breaker_open_total.labels(service="llm_primary").inc()
        except Exception:
            pass  # Never let metrics errors affect circuit breaker logic
