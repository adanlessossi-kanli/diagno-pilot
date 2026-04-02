"""
PrescriptionService cache integration tests — Diagno-Pilot

Feature: caching-and-performance

Property 2: Protocol cache round-trip
**Validates: Requirements 2.1, 2.2, 2.3**

Property 9: Cache invalidation on admin write
**Validates: Requirements 2.4, 3.4**

Unit tests for PrescriptionService cache integration
**Validates: Requirements 2.2, 2.3, 2.6**
"""
from __future__ import annotations

import dataclasses
import json
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.core.cache import CacheService
from backend.core.config import Settings
from backend.models.common import AgeGroup
from backend.services.prescription_service import (
    ANTIBIOTIC_PROTOCOLS,
    AntibioticProtocol,
    PrescriptionService,
    _doc_to_protocol,
)


# ---------------------------------------------------------------------------
# Helpers / strategies
# ---------------------------------------------------------------------------

def _make_cache_service() -> tuple[CacheService, fakeredis.FakeAsyncRedis]:
    """Return a CacheService wired to a FakeAsyncRedis instance."""
    svc = CacheService(Settings())
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    svc._client = fake
    svc._degraded = False
    return svc, fake


# Hypothesis strategy for AntibioticProtocol
_age_group_strategy = st.sampled_from(list(AgeGroup))

_protocol_strategy = st.builds(
    AntibioticProtocol,
    name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-")),
    paediatric_dose_per_kg=st.floats(min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False),
    adult_max_dose_mg=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    frequency=st.sampled_from(["1x/day", "2x/day", "3x/day", "4x/day"]),
    duration_days=st.integers(min_value=1, max_value=30),
    route=st.sampled_from(["oral", "IV", "IM"]),
    renal_adjustment_factor=st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
    hepatic_adjustment_factor=st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
    contraindicated_age_groups=st.lists(_age_group_strategy, max_size=3),
    alternative=st.one_of(st.none(), st.text(min_size=1, max_size=30)),
)


# ---------------------------------------------------------------------------
# Property 2 — Protocol cache round-trip
# ---------------------------------------------------------------------------

@given(protocol=_protocol_strategy)
@h_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_p2_protocol_cache_round_trip(protocol: AntibioticProtocol):
    # Feature: caching-and-performance, Property 2: protocol cache round-trip
    cache_svc, fake = _make_cache_service()
    try:
        key = cache_svc.make_key("protocol", protocol.name)
        serialised = json.dumps(dataclasses.asdict(protocol))
        await cache_svc.set(key, serialised, ttl=3600)
        raw = await cache_svc.get(key)
        assert raw is not None
        restored = _doc_to_protocol(json.loads(raw))
        assert restored == protocol
    finally:
        await fake.aclose()


# ---------------------------------------------------------------------------
# Property 9 — Cache invalidation on admin write
# ---------------------------------------------------------------------------

@given(
    name=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=["Ll"], whitelist_characters="-"),
    )
)
@h_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_p9_protocol_cache_invalidation_on_admin_write(name: str):
    # Feature: caching-and-performance, Property 9: cache invalidation on admin write
    cache_svc, fake = _make_cache_service()
    try:
        key = cache_svc.make_key("protocol", name)
        # Simulate a cached protocol entry
        await cache_svc.set(key, json.dumps({"name": name}), ttl=3600)
        assert await cache_svc.get(key) is not None

        # Admin write: delete the key
        await cache_svc.delete(key)

        # After invalidation, get must return None
        assert await cache_svc.get(key) is None
    finally:
        await fake.aclose()


@given(
    name=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=["Ll"], whitelist_characters="-"),
    )
)
@h_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_p9_drug_interaction_cache_invalidation_on_admin_write(name: str):
    # Feature: caching-and-performance, Property 9: cache invalidation on admin write
    cache_svc, fake = _make_cache_service()
    try:
        key = cache_svc.make_key("drug_interactions", "all")
        # Simulate a cached interactions entry
        await cache_svc.set(key, json.dumps([]), ttl=3600)
        assert await cache_svc.get(key) is not None

        # Admin write: delete the key
        await cache_svc.delete(key)

        # After invalidation, get must return None
        assert await cache_svc.get(key) is None
    finally:
        await fake.aclose()


# ---------------------------------------------------------------------------
# Unit tests — PrescriptionService cache integration (Task 4.3)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_skips_mongodb():
    """Cache hit: mock cache_service.get() returns serialised protocol; MongoDB not queried."""
    svc = PrescriptionService()
    protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
    serialised = json.dumps(dataclasses.asdict(protocol))

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.get = AsyncMock(return_value=serialised)
    mock_cache.make_key = MagicMock(return_value="v1:protocol:amoxicillin")

    with patch("backend.core.cache.cache_service", mock_cache):
        result = await svc._get_protocol("amoxicillin")

    assert result == protocol
    mock_cache.get.assert_called_once_with("v1:protocol:amoxicillin")


@pytest.mark.asyncio
async def test_cache_miss_falls_back_to_in_process_dict():
    """Cache miss: protocol is fetched from in-process dict when Redis returns None."""
    svc = PrescriptionService()
    protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
    svc._protocols_cache = {"amoxicillin": protocol}

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.make_key = MagicMock(return_value="v1:protocol:amoxicillin")

    with patch("backend.core.cache.cache_service", mock_cache):
        result = await svc._get_protocol("amoxicillin")

    assert result == protocol
    mock_cache.get.assert_called_once()


@pytest.mark.asyncio
async def test_cache_miss_falls_back_to_builtin_dict():
    """Cache miss + empty in-process dict: falls back to ANTIBIOTIC_PROTOCOLS."""
    svc = PrescriptionService()
    svc._protocols_cache = {}  # empty in-process cache

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.make_key = MagicMock(return_value="v1:protocol:amoxicillin")

    with patch("backend.core.cache.cache_service", mock_cache):
        result = await svc._get_protocol("amoxicillin")

    assert result == ANTIBIOTIC_PROTOCOLS["amoxicillin"]


@pytest.mark.asyncio
async def test_degraded_mode_falls_back_to_in_process_dict():
    """Degraded mode: CacheService.get() returns None; service uses in-process dict."""
    svc = PrescriptionService()
    protocol = ANTIBIOTIC_PROTOCOLS["ceftriaxone"]
    svc._protocols_cache = {"ceftriaxone": protocol}

    mock_cache = AsyncMock()
    mock_cache.is_degraded = True
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.make_key = MagicMock(return_value="v1:protocol:ceftriaxone")

    with patch("backend.core.cache.cache_service", mock_cache):
        result = await svc._get_protocol("ceftriaxone")

    assert result == protocol


@pytest.mark.asyncio
async def test_load_protocols_stores_in_cache():
    """load_protocols_from_db() stores each protocol in Redis after loading from MongoDB."""
    svc = PrescriptionService()

    # Mock MongoDB to return one protocol document
    protocol_doc = {
        "name": "amoxicillin",
        "paediatric_dose_per_kg": 50.0,
        "adult_max_dose_mg": 3000.0,
        "frequency": "3x/day",
        "duration_days": 7,
        "route": "oral",
        "renal_adjustment_factor": 0.5,
        "hepatic_adjustment_factor": 1.0,
        "contraindicated_age_groups": [],
        "alternative": None,
    }

    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=[protocol_doc])
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
            await svc.load_protocols_from_db()

    # Verify cache.set was called for the protocol (key includes region suffix)
    mock_cache.set.assert_called_once()
    call_args = mock_cache.set.call_args
    # Key format is v1:protocol:<name>:<region>; doc has no region so defaults to "ALL"
    assert call_args[0][0] == "v1:protocol:amoxicillin:ALL"
    stored = json.loads(call_args[0][1])
    assert stored["name"] == "amoxicillin"


@pytest.mark.asyncio
async def test_reload_protocols_invalidates_single_key():
    """reload_protocols(name=...) deletes the specific protocol key before reloading."""
    svc = PrescriptionService()

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.make_key = MagicMock(side_effect=lambda d, i: f"v1:{d}:{i}")
    mock_cache.delete = AsyncMock()
    mock_cache.flush_pattern = AsyncMock(return_value=0)
    mock_cache.set = AsyncMock()

    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(return_value=mock_cursor)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch("backend.core.cache.cache_service", mock_cache):
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            await svc.reload_protocols(name="amoxicillin")

    # reload_protocols(name=...) deletes keys for all regions (TG, BJ, ALL)
    assert mock_cache.delete.call_count == 3
    deleted_keys = {call.args[0] for call in mock_cache.delete.call_args_list}
    assert deleted_keys == {
        "v1:protocol:amoxicillin:TG",
        "v1:protocol:amoxicillin:BJ",
        "v1:protocol:amoxicillin:ALL",
    }
    mock_cache.flush_pattern.assert_not_called()


@pytest.mark.asyncio
async def test_reload_protocols_flushes_all_keys_when_no_name():
    """reload_protocols() without name flushes all protocol:* keys."""
    svc = PrescriptionService()

    mock_cache = AsyncMock()
    mock_cache.is_degraded = False
    mock_cache.make_key = MagicMock(side_effect=lambda d, i: f"v1:{d}:{i}")
    mock_cache.delete = AsyncMock()
    mock_cache.flush_pattern = AsyncMock(return_value=5)
    mock_cache.set = AsyncMock()

    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(return_value=mock_cursor)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch("backend.core.cache.cache_service", mock_cache):
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            await svc.reload_protocols()

    mock_cache.flush_pattern.assert_called_once_with("v1:protocol:*")
    mock_cache.delete.assert_not_called()
