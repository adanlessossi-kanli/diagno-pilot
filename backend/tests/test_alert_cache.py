"""
AlertService cache integration tests — Diagno-Pilot

Feature: caching-and-performance

Property 3: Interaction cache round-trip
**Validates: Requirements 3.1, 3.2, 3.3**

Unit tests for AlertService cache integration
**Validates: Requirements 3.2, 3.3, 3.5**
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.core.cache import CacheService
from backend.core.config import Settings
from backend.services.alert_service import AlertService


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
# Property 3 — Interaction cache round-trip
# ---------------------------------------------------------------------------

# Feature: caching-and-performance, Property 3: Interaction cache round-trip
# Validates: Requirements 3.1, 3.2, 3.3

@given(interactions=st.lists(st.tuples(st.text(), st.text(), st.text()), min_size=0, max_size=20))
@h_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_p3_interaction_cache_round_trip(interactions: list[tuple[str, str, str]]):
    """Store interaction list in cache, retrieve and deserialise, assert equal to original."""
    cache_svc, fake = _make_cache_service()
    try:
        key = cache_svc.make_key("drug_interactions", "all")
        serialised = json.dumps(interactions)
        await cache_svc.set(key, serialised, ttl=3600)
        raw = await cache_svc.get(key)
        assert raw is not None
        restored = [tuple(item) for item in json.loads(raw)]
        assert restored == [tuple(item) for item in interactions]
    finally:
        await fake.aclose()


# ---------------------------------------------------------------------------
# Unit tests — AlertService cache integration (Task 5.2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_skips_mongodb():
    """Cache hit: mock cache_service.get() returns serialised list; MongoDB not queried."""
    svc = AlertService()
    interactions = [("amoxicillin", "warfarin", "Test interaction")]
    serialised = json.dumps(interactions)

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.get = AsyncMock(return_value=serialised)
    mock_cache.make_key = MagicMock(return_value="v1:drug_interactions:all")

    with patch("backend.core.cache.cache_service", mock_cache):
        result = await svc._get_interactions()

    assert result == [("amoxicillin", "warfarin", "Test interaction")]
    mock_cache.get.assert_called_once_with("v1:drug_interactions:all")


@pytest.mark.asyncio
async def test_cache_miss_falls_back_to_in_process_list():
    """Cache miss: mock cache_service.get() returns None; in-process list is used."""
    svc = AlertService()
    svc._interactions_cache = [("drug_x", "drug_y", "Some interaction")]

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.make_key = MagicMock(return_value="v1:drug_interactions:all")

    with patch("backend.core.cache.cache_service", mock_cache):
        result = await svc._get_interactions()

    assert result == [("drug_x", "drug_y", "Some interaction")]
    mock_cache.get.assert_called_once()


@pytest.mark.asyncio
async def test_degraded_mode_falls_back_to_in_process_list():
    """Degraded mode: cache returns None; in-process list is used."""
    svc = AlertService()
    svc._interactions_cache = [("drug_a", "drug_b", "Degraded fallback")]

    mock_cache = AsyncMock()
    mock_cache.is_degraded = True
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.make_key = MagicMock(return_value="v1:drug_interactions:all")

    with patch("backend.core.cache.cache_service", mock_cache):
        result = await svc._get_interactions()

    assert result == [("drug_a", "drug_b", "Degraded fallback")]


@pytest.mark.asyncio
async def test_load_interactions_stores_in_cache():
    """load_interactions_from_db() stores the interaction list in Redis after loading from MongoDB."""
    svc = AlertService()

    mock_docs = [
        {"drug_a": "amoxicillin", "drug_b": "warfarin", "message": "Test interaction"},
    ]
    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=mock_docs)
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(return_value=mock_cursor)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.make_key = MagicMock(side_effect=lambda d, i: f"v1:{d}:{i}")
    mock_cache.set = AsyncMock()

    with patch("backend.core.cache.cache_service", mock_cache):
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            await svc.load_interactions_from_db()

    mock_cache.set.assert_called_once()
    call_args = mock_cache.set.call_args
    assert call_args[0][0] == "v1:drug_interactions:all"
    stored = json.loads(call_args[0][1])
    assert stored == [["amoxicillin", "warfarin", "Test interaction"]]


@pytest.mark.asyncio
async def test_reload_interactions_invalidates_cache_key():
    """reload_interactions() calls cache_service.delete() with v1:drug_interactions:all."""
    svc = AlertService()

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.make_key = MagicMock(side_effect=lambda d, i: f"v1:{d}:{i}")
    mock_cache.delete = AsyncMock()
    mock_cache.set = AsyncMock()

    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(return_value=mock_cursor)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch("backend.core.cache.cache_service", mock_cache):
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            await svc.reload_interactions()

    mock_cache.delete.assert_called_once_with("v1:drug_interactions:all")
