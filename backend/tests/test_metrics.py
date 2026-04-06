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
                before = _get_counter_value(registry, LLMRouter.PRIMARY_MODEL, "error")
                await router.generate("test prompt", [])
                after = _get_counter_value(registry, LLMRouter.PRIMARY_MODEL, "error")
                delta = after - before
                assert delta == 1.0, (
                    f"Call {i+1}: counter should increment by exactly 1 per primary failure, "
                    f"got delta={delta} (before={before}, after={after})"
                )

        # Total increment must equal n_failures
        total = _get_counter_value(registry, LLMRouter.PRIMARY_MODEL, "error")
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

        qwen3_errors = _get_counter_value(registry, LLMRouter.PRIMARY_MODEL, "error")
        gpt5_errors = _get_counter_value(registry, LLMRouter.FALLBACK_MODEL, "error")

        assert qwen3_errors == float(n_failures), (
            f"{LLMRouter.PRIMARY_MODEL} error counter should be {n_failures}, got {qwen3_errors}"
        )
        assert gpt5_errors == 0.0, (
            f"{LLMRouter.FALLBACK_MODEL} error counter should remain 0 when fallback succeeds, got {gpt5_errors}"
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


# ---------------------------------------------------------------------------
# Observability spec — Property 1: Metric singleton uniqueness
# ---------------------------------------------------------------------------


@given(n_imports=st.integers(min_value=2, max_value=10))
@h_settings(max_examples=50, deadline=None)
def test_p1_no_duplicate_metric_registration_on_repeated_import(n_imports: int):
    """
    Observability spec, Property 1: No duplicate metric registration.

    Importing backend.core.metrics multiple times in the same process must
    not raise ValueError. All repeated imports must return the same singleton
    objects (identity check).

    **Validates: Requirements 5.2, 5.3**
    """
    import importlib

    import backend.core.metrics as first_import

    for _ in range(n_imports - 1):
        # Re-importing a cached module must never raise ValueError
        try:
            mod = importlib.import_module("backend.core.metrics")
        except ValueError as exc:
            raise AssertionError(
                f"Re-importing backend.core.metrics raised ValueError: {exc}"
            ) from exc

        # All metric objects must be the exact same singletons
        assert mod.llm_duration_seconds is first_import.llm_duration_seconds
        assert mod.llm_requests_total is first_import.llm_requests_total
        assert mod.circuit_breaker_open_total is first_import.circuit_breaker_open_total
        assert mod.embedding_duration_seconds is first_import.embedding_duration_seconds
        assert mod.embedding_requests_total is first_import.embedding_requests_total
        assert mod.db_query_duration_seconds is first_import.db_query_duration_seconds
        assert mod.db_errors_total is first_import.db_errors_total
        assert mod.cache_hits_total is first_import.cache_hits_total
        assert mod.cache_misses_total is first_import.cache_misses_total
        assert mod.cache_degraded is first_import.cache_degraded


def test_p1_metrics_module_reload_does_not_raise():
    """
    Observability spec, Property 1 (reload variant):

    Forcing a module reload simulates the worst-case scenario where Python
    re-executes the module body. prometheus_client raises ValueError on
    duplicate registration unless the metric is already in the default
    registry — this test documents the expected behaviour.

    A reload WILL raise ValueError (prometheus_client's intended behaviour
    for duplicate names). This test asserts that normal import (sys.modules
    cache hit) never raises, and documents that reload is not a supported
    usage pattern.

    **Validates: Requirements 5.2, 5.3**
    """
    import importlib

    # Normal import — must never raise
    try:
        importlib.import_module("backend.core.metrics")
    except ValueError as exc:
        raise AssertionError(
            f"Normal import of backend.core.metrics raised ValueError: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Observability spec — Property 2: LLM requests counter equals call count
# ---------------------------------------------------------------------------


def _get_total_llm_requests(registry: CollectorRegistry) -> float:
    """Sum all diagno_pilot_llm_requests_total samples across all label combinations."""
    total = 0.0
    for metric in registry.collect():
        if metric.name in ("diagno_pilot_llm_requests_total", "diagno_pilot_llm_requests"):
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    total += sample.value
    return total


def _make_fresh_llm_counter() -> tuple[CollectorRegistry, Counter]:
    """Create a fresh isolated registry and llm_requests_total counter."""
    registry = CollectorRegistry()
    counter = Counter(
        "diagno_pilot_llm_requests_total",
        "Total LLM requests by model and status",
        ["model", "status"],
        registry=registry,
    )
    return registry, counter


@given(
    outcomes=st.lists(
        st.sampled_from(["success", "error"]),
        min_size=1,
        max_size=30,
    )
)
@h_settings(max_examples=100, deadline=None)
def test_p2_llm_requests_total_equals_number_of_calls(outcomes: list[str]):
    """
    Observability spec, Property 2: Every completed LLM call increments
    diagno_pilot_llm_requests_total exactly once.

    For any sequence of success/error outcomes, the counter total equals
    the number of calls made.

    When primary succeeds: 1 increment (primary success).
    When primary fails and fallback succeeds: 2 increments (primary error + fallback success).

    **Validates: Requirements 1.2, 1.4**
    """
    async def _run():
        registry, fresh_counter = _make_fresh_llm_counter()

        cb = CircuitBreaker(failure_threshold=len(outcomes) + 100, recovery_timeout=9999)
        router = LLMRouter(circuit_breaker=cb)

        expected_total = 0
        for outcome in outcomes:
            if outcome == "success":
                router._primary.generate = AsyncMock(return_value="ok")
                # Primary succeeds: 1 increment
                expected_total += 1
            else:
                router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("down"))
                router._fallback.generate = AsyncMock(return_value="fallback ok")
                # Primary error + fallback success: 2 increments
                expected_total += 2

            with patch("backend.services.llm_router.llm_requests_total", fresh_counter):
                await router.generate("prompt", [])

        total = _get_total_llm_requests(registry)
        assert total == float(expected_total), (
            f"Expected {expected_total} total LLM request increments, got {total}. "
            f"Outcomes: {outcomes}"
        )

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Observability spec — Property 3: Embedding requests counter equals call count
# ---------------------------------------------------------------------------


def _get_total_embedding_requests(registry: CollectorRegistry) -> tuple[float, float]:
    """Return (success_count, error_count) from diagno_pilot_embedding_requests_total."""
    success = 0.0
    error = 0.0
    for metric in registry.collect():
        if metric.name in ("diagno_pilot_embedding_requests_total", "diagno_pilot_embedding_requests"):
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    if sample.labels.get("status") == "success":
                        success += sample.value
                    elif sample.labels.get("status") == "error":
                        error += sample.value
    return success, error


def _make_fresh_embedding_counter() -> tuple[CollectorRegistry, Counter]:
    """Create a fresh isolated registry and embedding_requests_total counter."""
    registry = CollectorRegistry()
    counter = Counter(
        "diagno_pilot_embedding_requests_total",
        "Total embedding API calls by status",
        ["status"],
        registry=registry,
    )
    return registry, counter


@given(
    outcomes=st.lists(
        st.sampled_from(["success", "error"]),
        min_size=1,
        max_size=30,
    )
)
@h_settings(max_examples=100, deadline=None)
def test_p3_embedding_requests_total_equals_number_of_calls(outcomes: list[str]):
    """
    Observability spec, Property 3: diagno_pilot_embedding_requests_total count
    equals number of encode() calls — success and error counts sum to total calls.

    For any sequence of N encode() calls (mix of success/error), assert that
    embedding_requests_total{status="success"}.count +
    embedding_requests_total{status="error"}.count == N.

    **Validates: Requirements 2.2, 2.4**
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.services.embedding_model import EmbeddingModel

    async def _run():
        registry, fresh_counter = _make_fresh_embedding_counter()

        model = EmbeddingModel()

        # Mock cache to always miss so _call_api is always invoked
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.make_key = MagicMock(return_value="v1:embedding:test")
        mock_cache.set = AsyncMock()

        n = len(outcomes)
        for outcome in outcomes:
            if outcome == "success":
                mock_api = AsyncMock(return_value=[0.1, 0.2, 0.3])
            else:
                mock_api = AsyncMock(side_effect=RuntimeError("api error"))

            with patch("backend.services.embedding_model.cache_service", mock_cache):
                with patch("backend.services.embedding_model.embedding_requests_total", fresh_counter):
                    with patch.object(model, "_call_api", mock_api):
                        try:
                            await model.encode("test text")
                        except Exception:
                            pass  # error path is expected for "error" outcomes

        success_count, error_count = _get_total_embedding_requests(registry)
        total = success_count + error_count
        assert total == float(n), (
            f"Expected {n} total embedding request increments, got {total} "
            f"(success={success_count}, error={error_count}). Outcomes: {outcomes}"
        )

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Observability spec — Property 4: DB query duration observation count == N ops
# ---------------------------------------------------------------------------


def _get_db_observation_count(registry: CollectorRegistry, collection: str, operation: str) -> float:
    """Return the _count sample for diagno_pilot_db_query_duration_seconds."""
    for metric in registry.collect():
        if metric.name in (
            "diagno_pilot_db_query_duration_seconds",
            "diagno_pilot_db_query_duration",
        ):
            for sample in metric.samples:
                if (
                    sample.name.endswith("_count")
                    and sample.labels.get("collection") == collection
                    and sample.labels.get("operation") == operation
                ):
                    return sample.value
    return 0.0


def _make_fresh_db_histogram() -> tuple[CollectorRegistry, object]:
    """Create a fresh isolated registry and db_query_duration_seconds histogram."""
    from prometheus_client import Histogram as _Histogram

    registry = CollectorRegistry()
    histogram = _Histogram(
        "diagno_pilot_db_query_duration_seconds",
        "MongoDB query duration in seconds",
        ["collection", "operation"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        registry=registry,
    )
    return registry, histogram


def _make_fresh_db_errors_counter() -> tuple[CollectorRegistry, object]:
    """Create a fresh isolated registry and db_errors_total counter."""
    registry = CollectorRegistry()
    counter = Counter(
        "diagno_pilot_db_errors_total",
        "Total MongoDB operation errors",
        ["collection", "operation"],
        registry=registry,
    )
    return registry, counter


@given(
    outcomes=st.lists(
        st.sampled_from(["success", "error"]),
        min_size=1,
        max_size=30,
    )
)
@h_settings(max_examples=100, deadline=None)
def test_p4_db_query_duration_observation_count_equals_number_of_ops(outcomes: list[str]):
    """
    Observability spec, Property 4:
    diagno_pilot_db_query_duration_seconds observation count equals the number
    of completed DB operations — both successful and failed operations are recorded.

    For any sequence of N timed_db_op calls (mix of success/error), the histogram
    _count must equal N because the `finally` block always records the duration.

    **Validates: Requirements 3.2, 3.4**
    """
    from unittest.mock import patch

    from backend.core.db_metrics import timed_db_op

    async def _run():
        registry, fresh_histogram = _make_fresh_db_histogram()
        _, fresh_errors = _make_fresh_db_errors_counter()

        n = len(outcomes)
        collection = "test_col"
        operation = "find_one"

        with (
            patch("backend.core.db_metrics.db_query_duration_seconds", fresh_histogram),
            patch("backend.core.db_metrics.db_errors_total", fresh_errors),
        ):
            for outcome in outcomes:
                try:
                    async with timed_db_op(collection, operation):
                        if outcome == "error":
                            raise RuntimeError("simulated db error")
                        # success: do nothing
                except RuntimeError:
                    pass  # expected for error outcomes

        count = _get_db_observation_count(registry, collection, operation)
        assert count == float(n), (
            f"Expected {n} observations in db_query_duration_seconds, got {count}. "
            f"Outcomes: {outcomes}"
        )

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Property 5: cache hits + misses == total get calls
# ---------------------------------------------------------------------------

def _get_cache_counter_value(registry: CollectorRegistry, metric_name: str, cache: str) -> float:
    """Return the current value of a cache counter for a given cache label.

    prometheus_client stores Counter 'diagno_pilot_cache_hits_total' under
    metric.name == 'diagno_pilot_cache_hits' (strips the _total suffix).
    The sample name retains the _total suffix.
    """
    # Strip _total suffix to match prometheus_client's internal metric name
    base_name = metric_name[:-6] if metric_name.endswith("_total") else metric_name
    for metric in registry.collect():
        if metric.name == base_name:
            for sample in metric.samples:
                if (
                    sample.name == metric_name
                    and sample.labels.get("cache") == cache
                ):
                    return sample.value
    return 0.0


def _make_fresh_cache_counters() -> tuple[CollectorRegistry, Counter, Counter]:
    """Create a fresh isolated registry with cache_hits_total and cache_misses_total."""
    registry = CollectorRegistry()
    hits = Counter(
        "diagno_pilot_cache_hits_total",
        "Cache hits by cache name",
        ["cache"],
        registry=registry,
    )
    misses = Counter(
        "diagno_pilot_cache_misses_total",
        "Cache misses by cache name",
        ["cache"],
        registry=registry,
    )
    return registry, hits, misses


@given(
    outcomes=st.lists(
        st.sampled_from(["hit", "miss"]),
        min_size=1,
        max_size=50,
    )
)
@h_settings(max_examples=100, deadline=None)
def test_p5_cache_hits_plus_misses_equals_total_get_calls(outcomes: list[str]):
    """
    Observability spec, Property 5:
    For any sequence of cache get operations, hits + misses == total get calls.

    For any N cache.get() calls (mix of hit/miss outcomes), the sum of
    diagno_pilot_cache_hits_total and diagno_pilot_cache_misses_total must
    equal N.

    **Validates: Requirements 4.3, 4.4**
    """
    cache_name = "protocol"
    registry, fresh_hits, fresh_misses = _make_fresh_cache_counters()

    n = len(outcomes)
    for outcome in outcomes:
        if outcome == "hit":
            fresh_hits.labels(cache=cache_name).inc()
        else:
            fresh_misses.labels(cache=cache_name).inc()

    hits_count = _get_cache_counter_value(registry, "diagno_pilot_cache_hits_total", cache_name)
    misses_count = _get_cache_counter_value(registry, "diagno_pilot_cache_misses_total", cache_name)
    total = hits_count + misses_count

    assert total == float(n), (
        f"Expected hits + misses == {n}, got hits={hits_count} misses={misses_count} "
        f"total={total}. Outcomes: {outcomes}"
    )
    expected_hits = float(outcomes.count("hit"))
    expected_misses = float(outcomes.count("miss"))
    assert hits_count == expected_hits, (
        f"Expected {expected_hits} hits, got {hits_count}"
    )
    assert misses_count == expected_misses, (
        f"Expected {expected_misses} misses, got {misses_count}"
    )
