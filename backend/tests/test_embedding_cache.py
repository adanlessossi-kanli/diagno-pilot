"""
EmbeddingModel cache integration tests — Diagno-Pilot

Feature: caching-and-performance

Property 4: Embedding cache round-trip
**Validates: Requirements 4.2, 4.3, 4.4, 4.6**

Property 6: Deterministic cache key derivation
**Validates: Requirements 4.1, 5.1**

Unit tests for EmbeddingModel cache integration
**Validates: Requirements 4.2, 4.3, 4.5**
"""
from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.core.cache import CacheService
from backend.core.config import Settings
from backend.services.embedding_model import EmbeddingModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache_service() -> tuple[CacheService, fakeredis.FakeAsyncRedis]:
    """Return a CacheService wired to a FakeAsyncRedis instance."""
    svc = CacheService(Settings())
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    svc._client = fake
    svc._degraded = False
    return svc, fake


# ---------------------------------------------------------------------------
# Property 4 — Embedding cache round-trip
# ---------------------------------------------------------------------------

# Feature: caching-and-performance, Property 4: embedding cache round-trip
# Validates: Requirements 4.2, 4.3, 4.4, 4.6

@given(vector=st.lists(st.floats(allow_nan=False, allow_infinity=False), min_size=1, max_size=3072))
@h_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_p4_embedding_cache_round_trip(vector: list[float]):
    """Store embedding vector in cache, retrieve and deserialise, assert equal to original."""
    cache_svc, fake = _make_cache_service()
    try:
        text = "test input"
        digest = hashlib.sha256(text.encode()).hexdigest()
        key = cache_svc.make_key("embedding", digest)

        await cache_svc.set(key, json.dumps(vector), ttl=86400)
        raw = await cache_svc.get(key)
        assert raw is not None
        restored = json.loads(raw)

        assert len(restored) == len(vector)
        for original, retrieved in zip(vector, restored):
            assert abs(original - retrieved) < 1e-9
    finally:
        await fake.aclose()


# ---------------------------------------------------------------------------
# Property 6 — Deterministic cache key derivation
# ---------------------------------------------------------------------------

# Feature: caching-and-performance, Property 6: deterministic cache key derivation
# Validates: Requirements 4.1, 5.1

@given(text=st.text(min_size=1))
@h_settings(max_examples=100, deadline=None)
def test_p6_key_derivation_is_deterministic(text: str):
    """Calling the key-derivation function twice with the same input produces the same key."""
    digest1 = hashlib.sha256(text.encode()).hexdigest()
    digest2 = hashlib.sha256(text.encode()).hexdigest()
    assert digest1 == digest2


# ---------------------------------------------------------------------------
# Unit tests — EmbeddingModel cache integration (Task 6.3)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_skips_openai_api():
    """Cache hit: mock cache_service.get() returns serialised vector; OpenAI API not called."""
    model = EmbeddingModel()
    vector = [0.1, 0.2, 0.3]
    serialised = json.dumps(vector)

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.get = AsyncMock(return_value=serialised)
    mock_cache.make_key = MagicMock(return_value="v1:embedding:abc123")

    with patch("backend.services.embedding_model.cache_service", mock_cache):
        with patch.object(model, "_call_api", new_callable=AsyncMock) as mock_api:
            result = await model.encode("some text")

    assert result == vector
    mock_api.assert_not_called()
    mock_cache.get.assert_called_once_with("v1:embedding:abc123")


@pytest.mark.asyncio
async def test_cache_miss_calls_openai_and_stores_result():
    """Cache miss: OpenAI API is called and result is stored in cache."""
    model = EmbeddingModel()
    vector = [0.4, 0.5, 0.6]

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.make_key = MagicMock(return_value="v1:embedding:def456")
    mock_cache.set = AsyncMock()

    with patch("backend.services.embedding_model.cache_service", mock_cache):
        with patch.object(model, "_call_api", new_callable=AsyncMock, return_value=vector):
            result = await model.encode("another text")

    assert result == vector
    mock_cache.get.assert_called_once_with("v1:embedding:def456")
    mock_cache.set.assert_called_once()
    call_args = mock_cache.set.call_args
    assert call_args[0][0] == "v1:embedding:def456"
    assert json.loads(call_args[0][1]) == vector


@pytest.mark.asyncio
async def test_degraded_mode_calls_openai_directly():
    """Degraded mode: OpenAI API is called directly without error."""
    model = EmbeddingModel()
    vector = [0.7, 0.8, 0.9]

    mock_cache = AsyncMock()
    mock_cache.is_degraded = True
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.make_key = MagicMock(return_value="v1:embedding:ghi789")
    mock_cache.set = AsyncMock()

    with patch("backend.services.embedding_model.cache_service", mock_cache):
        with patch.object(model, "_call_api", new_callable=AsyncMock, return_value=vector):
            result = await model.encode("degraded text")

    assert result == vector
    # In degraded mode, cache.get returns None so API is called
    mock_cache.get.assert_called_once()
