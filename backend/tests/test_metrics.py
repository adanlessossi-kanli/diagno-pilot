# Feature: diagno-pilot-improvements, Property 19: Compteur de métriques LLM s'incrémente à chaque échec
"""
Test de propriété pour les métriques LLM — Diagno-Pilot

Property 19 : Compteur de métriques LLM s'incrémente à chaque échec
**Validates: Requirements 18.2**

Pour tout appel au LLM primaire qui lève une LLMUnavailableError, le compteur
Prometheus diagno_pilot_llm_requests_total{model="qwen3", status="error"}
doit s'incrémenter exactement de 1.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from prometheus_client import CollectorRegistry, Counter

from backend.core.circuit_breaker import CircuitBreaker
from backend.services.llm_router import LLMRouter, LLMUnavailableError


def _get_counter_value(registry: CollectorRegistry, model: str, status: str) -> float:
    """Read the current value of diagno_pilot_llm_requests_total from a registry.

    prometheus_client stores the metric under the base name (without _total suffix),
    so we match on both the full name and the base name.
    """
    for metric in registry.collect():
        if metric.name in ("diagno_pilot_llm_requests_total", "diagno_pilot_llm_requests"):
            for sample in metric.samples:
                if (
                    sample.labels.get("model") == model
                    and sample.labels.get("status") == status
                    # Only count the _total sample, not the _created timestamp sample
                    and sample.name.endswith("_total")
                ):
                    return sample.value
    return 0.0


def _make_fresh_counter() -> tuple[CollectorRegistry, Counter]:
    """Create a fresh isolated Prometheus registry and counter for each test run."""
    registry = CollectorRegistry()
    counter = Counter(
        "diagno_pilot_llm_requests_total",
        "Total LLM requests by model and status",
        ["model", "status"],
        registry=registry,
    )
    return registry, counter


@given(n_failures=st.integers(min_value=1, max_value=20))
@h_settings(max_examples=100, deadline=None)
def test_p19_llm_error_counter_increments_by_one_per_failure(n_failures: int):
    """
    Feature: diagno-pilot-improvements, Property 19:
    Pour tout N ≥ 1 appels au LLM primaire qui lèvent LLMUnavailableError,
    le compteur diagno_pilot_llm_requests_total{model="qwen3", status="error"}
    doit s'incrémenter exactement de N (soit +1 par appel).

    **Validates: Requirements 18.2**
    """
    async def _run_test():
        registry, fresh_counter = _make_fresh_counter()

        # Use a circuit breaker with a very high threshold so it never opens
        # during the test — this ensures every call goes through the primary
        # and raises LLMUnavailableError (triggering the counter increment).
        cb = CircuitBreaker(failure_threshold=n_failures + 100, recovery_timeout=9999)
        router = LLMRouter(circuit_breaker=cb)

        # Mock primary to always raise LLMUnavailableError
        router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary down"))
        # Mock fallback to succeed (so we don't get HTTP 503)
        router._fallback.generate = AsyncMock(return_value="fallback ok")

        with patch("backend.services.llm_router.llm_requests_total", fresh_counter):
            for i in range(n_failures):
                before = _get_counter_value(registry, "qwen3", "error")
                await router.generate("test prompt", [])
                after = _get_counter_value(registry, "qwen3", "error")
                delta = after - before
                assert delta == 1.0, (
                    f"Call {i+1}: counter should increment by exactly 1 per primary failure, "
                    f"got delta={delta} (before={before}, after={after})"
                )

        # Total increment must equal n_failures
        total = _get_counter_value(registry, "qwen3", "error")
        assert total == float(n_failures), (
            f"After {n_failures} primary failures, counter should be {n_failures}, got {total}"
        )

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run_test())


@given(n_failures=st.integers(min_value=1, max_value=20))
@h_settings(max_examples=100, deadline=None)
def test_p19_fallback_success_does_not_affect_primary_error_counter(n_failures: int):
    """
    Feature: diagno-pilot-improvements, Property 19 (complement):
    Quand le fallback réussit après un échec primaire, seul le compteur
    {model="qwen3", status="error"} est incrémenté — pas {model="gpt5", status="error"}.

    **Validates: Requirements 18.2**
    """
    async def _run_test():
        registry, fresh_counter = _make_fresh_counter()

        cb = CircuitBreaker(failure_threshold=n_failures + 100, recovery_timeout=9999)
        router = LLMRouter(circuit_breaker=cb)
        router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary down"))
        router._fallback.generate = AsyncMock(return_value="fallback ok")

        with patch("backend.services.llm_router.llm_requests_total", fresh_counter):
            for _ in range(n_failures):
                await router.generate("test prompt", [])

        qwen3_errors = _get_counter_value(registry, "qwen3", "error")
        gpt5_errors = _get_counter_value(registry, "gpt5", "error")

        assert qwen3_errors == float(n_failures), (
            f"qwen3 error counter should be {n_failures}, got {qwen3_errors}"
        )
        assert gpt5_errors == 0.0, (
            f"gpt5 error counter should remain 0 when fallback succeeds, got {gpt5_errors}"
        )

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run_test())


# ---------------------------------------------------------------------------
# Unit test — /metrics endpoint exposes cache metrics (Task 11.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_endpoint_contains_cache_metrics():
    """Assert /metrics response body contains cache_hits_total, cache_misses_total, cache_degraded.

    **Validates: Requirements 8.4**
    """
    # Import cache module to ensure metrics are registered in the default registry
    import backend.core.cache  # noqa: F401

    from backend.main import app

    # METRICS_AUTH is not set in .env so unauthenticated access is allowed
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "cache_hits_total" in body, "cache_hits_total not found in /metrics output"
    assert "cache_misses_total" in body, "cache_misses_total not found in /metrics output"
    assert "cache_degraded" in body, "cache_degraded not found in /metrics output"
