# Feature: diagno-pilot-improvements, Property 8: Circuit breaker s'ouvre après N échecs consécutifs
# Feature: diagno-pilot-improvements, Property 9: Circuit breaker passe en half-open après la période de récupération
"""
Tests de propriété pour le CircuitBreaker — Diagno-Pilot

Property 8 : Circuit breaker s'ouvre après N échecs consécutifs
**Validates: Requirements 5.1, 5.2**

Pour tout nombre d'échecs consécutifs ≥ 5 sur le LLM primaire, le CircuitBreaker
doit passer à l'état OPEN et toute requête suivante doit lever CircuitOpenError
sans tenter le primaire.

Property 9 : Circuit breaker passe en half-open après la période de récupération
**Validates: Requirements 5.3**

Pour tout circuit en état OPEN, après un délai simulé de 120 secondes, le circuit
doit passer à l'état HALF_OPEN et laisser passer exactement une requête de test.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.core.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _failing_coro() -> None:
    """A coroutine that always raises LLMUnavailableError."""
    from backend.services.llm_router import LLMUnavailableError
    raise LLMUnavailableError("simulated primary failure")


async def _success_coro() -> str:
    return "ok"


async def _failing_fn(*args, **kwargs) -> None:
    """Callable version for call_fn tests."""
    from backend.services.llm_router import LLMUnavailableError
    raise LLMUnavailableError("simulated primary failure")


async def _success_fn(*args, **kwargs) -> str:
    return "ok"


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Property 8 — Circuit opens after N consecutive failures
# ---------------------------------------------------------------------------

@given(
    failure_threshold=st.integers(min_value=1, max_value=10),
    extra_failures=st.integers(min_value=0, max_value=5),
)
@h_settings(max_examples=100, deadline=None)
def test_p8_circuit_opens_after_n_failures(
    failure_threshold: int, extra_failures: int
):
    """
    Feature: diagno-pilot-improvements, Property 8:
    Pour tout failure_threshold ≥ 1, après exactement failure_threshold échecs
    consécutifs, le circuit doit être OPEN et les appels suivants doivent lever
    CircuitOpenError sans exécuter la coroutine.

    **Validates: Requirements 5.1, 5.2**
    """
    async def _run_test():
        cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=9999)

        # Trigger exactly failure_threshold failures
        for i in range(failure_threshold):
            assert cb.state == CircuitState.CLOSED, (
                f"Circuit should be CLOSED before threshold, was {cb.state} at failure {i}"
            )
            with pytest.raises(Exception):
                await cb.call(_failing_coro())

        # Circuit must now be OPEN
        assert cb.state == CircuitState.OPEN, (
            f"Circuit should be OPEN after {failure_threshold} failures, got {cb.state}"
        )

        # Any further call must raise CircuitOpenError immediately (no execution)
        for _ in range(extra_failures + 1):
            with pytest.raises(CircuitOpenError):
                await cb.call_fn(_success_fn)  # even a success fn must be blocked

        # State must remain OPEN (recovery_timeout not elapsed)
        assert cb.state == CircuitState.OPEN

    _run(_run_test())


@given(failure_threshold=st.integers(min_value=2, max_value=10))
@h_settings(max_examples=100, deadline=None)
def test_p8_circuit_stays_closed_below_threshold(failure_threshold: int):
    """
    Feature: diagno-pilot-improvements, Property 8 (complement):
    Le circuit reste CLOSED tant que le nombre d'échecs est strictement
    inférieur au seuil.

    **Validates: Requirements 5.1**
    """
    async def _run_test():
        cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=9999)

        # Fail (threshold - 1) times — circuit must stay CLOSED
        for i in range(failure_threshold - 1):
            with pytest.raises(Exception):
                await cb.call(_failing_coro())
            assert cb.state == CircuitState.CLOSED, (
                f"Circuit should remain CLOSED after {i+1} failures (threshold={failure_threshold})"
            )

    _run(_run_test())


@given(failure_threshold=st.integers(min_value=1, max_value=10))
@h_settings(max_examples=100, deadline=None)
def test_p8_success_resets_failure_count(failure_threshold: int):
    """
    Feature: diagno-pilot-improvements, Property 8 (reset):
    Un succès intercalé entre des échecs remet le compteur à zéro,
    empêchant l'ouverture du circuit.

    **Validates: Requirements 5.1**
    """
    async def _run_test():
        cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=9999)

        # Fail (threshold - 1) times, then succeed, then fail again
        for _ in range(failure_threshold - 1):
            with pytest.raises(Exception):
                await cb.call(_failing_coro())

        # Success resets the counter
        result = await cb.call(_success_coro())
        assert result == "ok"
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

        # Fail again — circuit should not open until threshold is reached again
        for i in range(failure_threshold - 1):
            with pytest.raises(Exception):
                await cb.call(_failing_coro())
            assert cb.state == CircuitState.CLOSED, (
                f"Circuit should remain CLOSED after reset + {i+1} failures"
            )

    _run(_run_test())


# ---------------------------------------------------------------------------
# Property 9 — Circuit transitions to HALF_OPEN after recovery_timeout
# ---------------------------------------------------------------------------

@given(
    failure_threshold=st.integers(min_value=1, max_value=5),
    recovery_timeout=st.floats(min_value=0.001, max_value=1.0),
)
@h_settings(max_examples=100, deadline=None)
def test_p9_circuit_transitions_to_half_open(
    failure_threshold: int, recovery_timeout: float
):
    """
    Feature: diagno-pilot-improvements, Property 9:
    Pour tout circuit en état OPEN, après un délai ≥ recovery_timeout,
    le circuit doit passer à l'état HALF_OPEN et laisser passer une requête.

    **Validates: Requirements 5.3**
    """
    async def _run_test():
        cb = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

        # Open the circuit
        for _ in range(failure_threshold):
            with pytest.raises(Exception):
                await cb.call(_failing_coro())

        assert cb.state == CircuitState.OPEN

        # Simulate time passing beyond recovery_timeout by patching time.monotonic
        fake_now = cb._opened_at + recovery_timeout + 0.001  # type: ignore[operator]
        with patch("backend.core.circuit_breaker.time.monotonic", return_value=fake_now):
            # The next call should be allowed through (HALF_OPEN probe)
            result = await cb.call_fn(_success_fn)

        assert result == "ok"
        # After a successful probe, circuit should close
        assert cb.state == CircuitState.CLOSED

    _run(_run_test())


@given(
    failure_threshold=st.integers(min_value=1, max_value=5),
    recovery_timeout=st.floats(min_value=0.001, max_value=1.0),
)
@h_settings(max_examples=100, deadline=None)
def test_p9_half_open_probe_failure_reopens_circuit(
    failure_threshold: int, recovery_timeout: float
):
    """
    Feature: diagno-pilot-improvements, Property 9 (probe failure):
    Si la requête de test en HALF_OPEN échoue, le circuit doit repasser à OPEN.

    **Validates: Requirements 5.3**
    """
    async def _run_test():
        cb = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

        # Open the circuit
        for _ in range(failure_threshold):
            with pytest.raises(Exception):
                await cb.call(_failing_coro())

        assert cb.state == CircuitState.OPEN

        # Advance time past recovery_timeout
        fake_now = cb._opened_at + recovery_timeout + 0.001  # type: ignore[operator]
        with patch("backend.core.circuit_breaker.time.monotonic", return_value=fake_now):
            # Probe fails — circuit should reopen
            with pytest.raises(Exception):
                await cb.call_fn(_failing_fn)

        assert cb.state == CircuitState.OPEN, (
            "Circuit should reopen after a failed HALF_OPEN probe"
        )

    _run(_run_test())


@given(
    failure_threshold=st.integers(min_value=1, max_value=5),
    elapsed_fraction=st.floats(min_value=0.0, max_value=0.999),
)
@h_settings(max_examples=100, deadline=None)
def test_p9_circuit_stays_open_before_recovery_timeout(
    failure_threshold: int, elapsed_fraction: float
):
    """
    Feature: diagno-pilot-improvements, Property 9 (complement):
    Le circuit reste OPEN si le délai écoulé est strictement inférieur
    à recovery_timeout.

    **Validates: Requirements 5.3**
    """
    recovery_timeout = 120.0

    async def _run_test():
        cb = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

        # Open the circuit
        for _ in range(failure_threshold):
            with pytest.raises(Exception):
                await cb.call(_failing_coro())

        assert cb.state == CircuitState.OPEN

        # Advance time to less than recovery_timeout
        elapsed = elapsed_fraction * recovery_timeout
        fake_now = cb._opened_at + elapsed  # type: ignore[operator]
        with patch("backend.core.circuit_breaker.time.monotonic", return_value=fake_now):
            with pytest.raises(CircuitOpenError):
                await cb.call_fn(_success_fn)

        assert cb.state == CircuitState.OPEN, (
            "Circuit should remain OPEN before recovery_timeout elapses"
        )

    _run(_run_test())


# ---------------------------------------------------------------------------
# Integration — LLMRouter uses circuit breaker
# ---------------------------------------------------------------------------

def test_llm_router_routes_to_fallback_when_circuit_open():
    """
    Feature: diagno-pilot-improvements, Property 8 (integration):
    Quand le circuit est OPEN, LLMRouter route directement vers le fallback
    sans tenter le primaire.

    **Validates: Requirements 5.2**
    """
    from backend.services.llm_router import LLMRouter, LLMUnavailableError

    async def _run_test():
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)

        # Open the circuit with one failure
        with pytest.raises(Exception):
            await cb.call(_failing_coro())

        assert cb.state == CircuitState.OPEN

        router = LLMRouter(circuit_breaker=cb)
        router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("should not be called"))
        router._fallback.generate = AsyncMock(return_value="fallback response")

        result = await router.generate("test prompt", [])
        assert result == "fallback response"
        assert router.last_used == "gpt5"

        # Primary must NOT have been called
        router._primary.generate.assert_not_called()

    _run(_run_test())


def test_llm_router_raises_503_when_both_llms_unavailable():
    """
    Feature: diagno-pilot-improvements, Property 8 (integration):
    Quand les deux LLM sont indisponibles, LLMRouter lève HTTP 503.

    **Validates: Requirements 5.5**
    """
    from fastapi import HTTPException
    from backend.services.llm_router import LLMRouter, LLMUnavailableError

    async def _run_test():
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)

        # Open the circuit
        with pytest.raises(Exception):
            await cb.call(_failing_coro())

        router = LLMRouter(circuit_breaker=cb)
        router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary down"))
        router._fallback.generate = AsyncMock(side_effect=LLMUnavailableError("fallback down"))

        with pytest.raises(HTTPException) as exc_info:
            await router.generate("test prompt", [])

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "llm_unavailable"

    _run(_run_test())
