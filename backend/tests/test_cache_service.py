"""
Unit and property tests for CacheService — Diagno-Pilot

Feature: caching-and-performance

Property 1: Degraded mode is a transparent no-op
**Validates: Requirements 1.4, 2.6, 3.5, 4.5, 5.6**

Property 7: Cache key format invariant
**Validates: Requirements 9.1, 9.2, 9.3**

Unit tests for CacheService
**Validates: Requirements 1.3, 1.4, 8.3**
"""
from __future__ import annotations

import pytest
import pytest_asyncio
import fakeredis
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from unittest.mock import AsyncMock, patch

from backend.core.cache import CacheService, cache_degraded
from backend.core.config import Settings


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_service(settings_obj: Settings | None = None) -> CacheService:
    """Create a CacheService backed by the given (or default) settings."""
    if settings_obj is None:
        settings_obj = Settings()
    return CacheService(settings_obj)


@pytest_asyncio.fixture
async def fake_redis_service():
    """CacheService wired to a FakeAsyncRedis instance (no live Redis needed)."""
    svc = _make_service()
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    svc._client = fake
    svc._degraded = False
    cache_degraded.set(0)
    yield svc
    await fake.aclose()


# ---------------------------------------------------------------------------
# Property 1 — Degraded mode is a transparent no-op
# ---------------------------------------------------------------------------

@given(key=st.text(min_size=1), value=st.text())
@h_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_p1_degraded_mode_get_returns_none(key: str, value: str):
    # Feature: caching-and-performance, Property 1: degraded mode is a transparent no-op
    svc = _make_service()
    svc._degraded = True
    result = await svc.get(key)
    assert result is None


@given(key=st.text(min_size=1), value=st.text())
@h_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_p1_degraded_mode_set_does_not_raise(key: str, value: str):
    # Feature: caching-and-performance, Property 1: degraded mode is a transparent no-op
    svc = _make_service()
    svc._degraded = True
    # Must not raise
    await svc.set(key, value, ttl=60)


# ---------------------------------------------------------------------------
# Property 7 — Cache key format invariant
# ---------------------------------------------------------------------------

@given(
    domain=st.text(min_size=1),
    identifier=st.text(min_size=1),
)
@h_settings(max_examples=100, deadline=None)
def test_p7_key_format_invariant(domain: str, identifier: str):
    # Feature: caching-and-performance, Property 7: cache key format invariant
    svc = _make_service()
    key = svc.make_key(domain, identifier)
    version = svc._settings.CACHE_KEY_VERSION
    assert key == f"{version}:{domain}:{identifier}"


@given(
    domain=st.text(min_size=1),
    identifier=st.text(min_size=1),
    version=st.text(min_size=1),
)
@h_settings(max_examples=100, deadline=None)
def test_p7_key_format_uses_settings_version(domain: str, identifier: str, version: str):
    # Feature: caching-and-performance, Property 7: cache key format invariant
    s = Settings(CACHE_KEY_VERSION=version)
    svc = _make_service(s)
    key = svc.make_key(domain, identifier)
    assert key.startswith(f"{version}:")
    assert key == f"{version}:{domain}:{identifier}"


# ---------------------------------------------------------------------------
# Unit tests — make_key()
# ---------------------------------------------------------------------------

def test_make_key_known_inputs():
    """make_key returns the expected versioned key for known inputs."""
    s = Settings(CACHE_KEY_VERSION="v1")
    svc = _make_service(s)
    assert svc.make_key("protocol", "amoxicillin") == "v1:protocol:amoxicillin"
    assert svc.make_key("drug_interactions", "all") == "v1:drug_interactions:all"
    assert svc.make_key("rag", "abc123") == "v1:rag:abc123"
    assert svc.make_key("embedding", "deadbeef") == "v1:embedding:deadbeef"


def test_make_key_custom_version():
    """make_key uses the version from settings."""
    s = Settings(CACHE_KEY_VERSION="v2")
    svc = _make_service(s)
    assert svc.make_key("protocol", "test") == "v2:protocol:test"


# ---------------------------------------------------------------------------
# Unit tests — degraded mode via ConnectionError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_degraded_on_connect_failure():
    """connect() failure puts the service in degraded mode."""
    svc = _make_service()
    # Patch from_url to return a client whose ping raises ConnectionError
    mock_client = AsyncMock()
    mock_client.ping.side_effect = ConnectionError("Redis unreachable")
    with patch("backend.core.cache.aioredis.from_url", return_value=mock_client):
        await svc.connect()
    assert svc.is_degraded is True


@pytest.mark.asyncio
async def test_get_returns_none_in_degraded_mode():
    """get() returns None when service is in degraded mode."""
    svc = _make_service()
    svc._degraded = True
    result = await svc.get("some:key")
    assert result is None


@pytest.mark.asyncio
async def test_set_is_noop_in_degraded_mode():
    """set() is a no-op when service is in degraded mode (no exception raised)."""
    svc = _make_service()
    svc._degraded = True
    # Should not raise
    await svc.set("some:key", '{"data": 1}', ttl=60)


@pytest.mark.asyncio
async def test_delete_is_noop_in_degraded_mode():
    """delete() is a no-op when service is in degraded mode."""
    svc = _make_service()
    svc._degraded = True
    await svc.delete("some:key")  # must not raise


@pytest.mark.asyncio
async def test_flush_pattern_returns_zero_in_degraded_mode():
    """flush_pattern() returns 0 when service is in degraded mode."""
    svc = _make_service()
    svc._degraded = True
    result = await svc.flush_pattern("v1:rag:*")
    assert result == 0


@pytest.mark.asyncio
async def test_get_enters_degraded_on_redis_error():
    """get() enters degraded mode when Redis raises an exception."""
    svc = _make_service()
    mock_client = AsyncMock()
    mock_client.get.side_effect = ConnectionError("lost connection")
    svc._client = mock_client
    svc._degraded = False

    result = await svc.get("some:key")
    assert result is None
    assert svc.is_degraded is True


@pytest.mark.asyncio
async def test_set_enters_degraded_on_redis_error():
    """set() enters degraded mode when Redis raises an exception."""
    svc = _make_service()
    mock_client = AsyncMock()
    mock_client.set.side_effect = ConnectionError("lost connection")
    svc._client = mock_client
    svc._degraded = False

    await svc.set("some:key", '{}', ttl=60)
    assert svc.is_degraded is True


# ---------------------------------------------------------------------------
# Unit tests — cache_degraded gauge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_degraded_gauge_set_to_1_in_degraded_mode():
    """cache_degraded gauge is 1 when service enters degraded mode."""
    svc = _make_service()
    mock_client = AsyncMock()
    mock_client.ping.side_effect = ConnectionError("Redis unreachable")
    with patch("backend.core.cache.aioredis.from_url", return_value=mock_client):
        await svc.connect()
    assert svc.is_degraded is True
    assert cache_degraded._value.get() == 1.0


@pytest.mark.asyncio
async def test_cache_degraded_gauge_set_to_0_when_healthy():
    """cache_degraded gauge is 0 when service connects successfully."""
    svc = _make_service()
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    with patch("backend.core.cache.aioredis.from_url", return_value=fake):
        await svc.connect()
    assert svc.is_degraded is False
    assert cache_degraded._value.get() == 0.0
    await fake.aclose()


# ---------------------------------------------------------------------------
# Unit tests — get/set/delete/flush_pattern with fakeredis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_and_get_roundtrip(fake_redis_service: CacheService):
    """set() then get() returns the stored value."""
    svc = fake_redis_service
    key = svc.make_key("protocol", "amoxicillin")
    value = '{"name": "amoxicillin"}'
    await svc.set(key, value, ttl=3600)
    result = await svc.get(key)
    assert result == value


@pytest.mark.asyncio
async def test_get_returns_none_for_missing_key(fake_redis_service: CacheService):
    """get() returns None for a key that does not exist."""
    svc = fake_redis_service
    result = await svc.get("v1:protocol:nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete_removes_key(fake_redis_service: CacheService):
    """delete() removes a key so subsequent get() returns None."""
    svc = fake_redis_service
    key = svc.make_key("protocol", "test")
    await svc.set(key, '{}', ttl=60)
    await svc.delete(key)
    assert await svc.get(key) is None


@pytest.mark.asyncio
async def test_flush_pattern_removes_matching_keys(fake_redis_service: CacheService):
    """flush_pattern() removes all keys matching the pattern."""
    svc = fake_redis_service
    keys = [svc.make_key("rag", f"hash{i}") for i in range(5)]
    for k in keys:
        await svc.set(k, '{}', ttl=300)
    # Also set a non-matching key
    other_key = svc.make_key("protocol", "amox")
    await svc.set(other_key, '{}', ttl=3600)

    deleted = await svc.flush_pattern(f"{svc._settings.CACHE_KEY_VERSION}:rag:*")
    assert deleted == 5
    for k in keys:
        assert await svc.get(k) is None
    # Non-matching key should still exist
    assert await svc.get(other_key) is not None


@pytest.mark.asyncio
async def test_get_deletes_corrupt_json_key(fake_redis_service: CacheService):
    """get() deletes a key with corrupt JSON and returns None."""
    svc = fake_redis_service
    key = svc.make_key("protocol", "corrupt")
    # Directly set corrupt data bypassing CacheService.set()
    await svc._client.set(key, "not-valid-json{{{")
    result = await svc.get(key)
    assert result is None
    # Key should have been deleted
    assert await svc._client.get(key) is None


@pytest.mark.asyncio
async def test_ping_returns_true_when_healthy(fake_redis_service: CacheService):
    """ping() returns True when Redis is reachable."""
    result = await fake_redis_service.ping()
    assert result is True


@pytest.mark.asyncio
async def test_ping_returns_false_when_client_is_none():
    """ping() returns False when no client is connected."""
    svc = _make_service()
    svc._client = None
    result = await svc.ping()
    assert result is False


# ---------------------------------------------------------------------------
# Property 10 — Metrics counters increment on every hit and miss
# ---------------------------------------------------------------------------

from prometheus_client import CollectorRegistry, Counter as PrometheusCounter  # noqa: E402
from backend.services.embedding_service import EmbeddingModel  # noqa: E402


def _get_sample_value(registry: CollectorRegistry, metric_name: str, cache_label: str) -> float:
    """Read the current value of a labelled counter from an isolated registry."""
    for metric in registry.collect():
        if metric.name in (metric_name, metric_name.replace("_total", "")):
            for sample in metric.samples:
                if (
                    sample.labels.get("cache") == cache_label
                    and sample.name.endswith("_total")
                ):
                    return sample.value
    return 0.0


@given(texts=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=3))
@h_settings(max_examples=50, deadline=None)
@pytest.mark.asyncio
async def test_p10_embedding_miss_then_hit_increments_counters(texts: list[str]):
    # Feature: caching-and-performance, Property 10: metrics counters increment on every hit and miss
    # **Validates: Requirements 8.1, 8.2**
    registry = CollectorRegistry()
    fresh_hits = PrometheusCounter("cache_hits_total", "Cache hits", ["cache"], registry=registry)
    fresh_misses = PrometheusCounter("cache_misses_total", "Cache misses", ["cache"], registry=registry)

    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    svc = CacheService(Settings())
    svc._client = fake
    svc._degraded = False

    embedder = EmbeddingModel()
    mock_vector = [0.1, 0.2, 0.3]

    unique_texts = list(dict.fromkeys(texts))  # deduplicate while preserving order

    with patch("backend.core.metrics.cache_hits_total", fresh_hits), \
         patch("backend.core.metrics.cache_misses_total", fresh_misses), \
         patch("backend.services.embedding_service.cache_service", svc), \
         patch("backend.services.embedding_service.cache_hits_total", fresh_hits), \
         patch("backend.services.embedding_service.cache_misses_total", fresh_misses), \
         patch.object(embedder, "_call_api", AsyncMock(return_value=mock_vector)):

        for text in unique_texts:
            # First call → cache miss: cache_misses_total must increment by 1
            before_miss = _get_sample_value(registry, "cache_misses_total", "embedding")
            await embedder.encode(text)
            after_miss = _get_sample_value(registry, "cache_misses_total", "embedding")
            assert after_miss == before_miss + 1.0, (
                f"cache_misses_total should increment by 1 on miss, "
                f"got delta={after_miss - before_miss}"
            )

            # Second call → cache hit: cache_hits_total must increment by 1
            before_hit = _get_sample_value(registry, "cache_hits_total", "embedding")
            await embedder.encode(text)
            after_hit = _get_sample_value(registry, "cache_hits_total", "embedding")
            assert after_hit == before_hit + 1.0, (
                f"cache_hits_total should increment by 1 on hit, "
                f"got delta={after_hit - before_hit}"
            )

    await fake.aclose()
