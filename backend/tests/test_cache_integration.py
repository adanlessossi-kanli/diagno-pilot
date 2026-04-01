"""
Integration tests for CacheService using fakeredis async variant.

Covers:
- Full get/set/delete/flush_pattern cycle (Requirements 1.1, 1.4)
- Key versioning — changing CACHE_KEY_VERSION isolates entries (Requirement 9.3)
- Degraded mode recovery — service exits degraded mode when Redis recovers (Requirement 1.6)
- Warm-up with mocked MongoDB — protocols and interactions are pre-populated (Requirement 10.1)
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest
import pytest_asyncio

from backend.core.cache import CacheService, cache_degraded
from backend.core.config import Settings
from backend.services.prescription_service import (
    ANTIBIOTIC_PROTOCOLS,
    PrescriptionService,
    _doc_to_protocol,
)
from backend.services.alert_service import AlertService, _DRUG_INTERACTIONS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_settings(**overrides) -> Settings:
    return Settings(**overrides)


@pytest_asyncio.fixture
async def fake_redis():
    """Bare FakeAsyncRedis instance — shared across tests that need direct access."""
    r = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest_asyncio.fixture
async def svc(fake_redis):
    """CacheService wired to a FakeAsyncRedis instance."""
    service = CacheService(_make_settings())
    service._client = fake_redis
    service._degraded = False
    cache_degraded.set(0)
    yield service


# ---------------------------------------------------------------------------
# 1. Full get / set / delete / flush_pattern cycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_then_get_returns_value(svc: CacheService):
    """set() stores a value that get() can retrieve. (Requirement 1.1)"""
    key = svc.make_key("protocol", "amoxicillin")
    payload = json.dumps({"name": "amoxicillin", "dose": 50})
    await svc.set(key, payload, ttl=3600)
    result = await svc.get(key)
    assert result == payload


@pytest.mark.asyncio
async def test_get_missing_key_returns_none(svc: CacheService):
    """get() returns None for a key that was never set. (Requirement 1.1)"""
    result = await svc.get(svc.make_key("protocol", "nonexistent"))
    assert result is None


@pytest.mark.asyncio
async def test_delete_removes_key(svc: CacheService):
    """delete() removes a key so subsequent get() returns None. (Requirement 1.1)"""
    key = svc.make_key("drug_interactions", "all")
    await svc.set(key, "[]", ttl=3600)
    assert await svc.get(key) is not None

    await svc.delete(key)
    assert await svc.get(key) is None


@pytest.mark.asyncio
async def test_flush_pattern_removes_all_matching_keys(svc: CacheService):
    """flush_pattern() deletes all keys matching the glob and returns the count. (Requirement 1.1)"""
    rag_keys = [svc.make_key("rag", f"hash{i}") for i in range(4)]
    other_key = svc.make_key("protocol", "amoxicillin")

    for k in rag_keys:
        await svc.set(k, "{}", ttl=300)
    await svc.set(other_key, "{}", ttl=3600)

    deleted = await svc.flush_pattern(svc.make_key("rag", "*"))
    assert deleted == 4

    for k in rag_keys:
        assert await svc.get(k) is None
    # Non-matching key must survive
    assert await svc.get(other_key) is not None


@pytest.mark.asyncio
async def test_flush_pattern_empty_keyspace_returns_zero(svc: CacheService):
    """flush_pattern() returns 0 when no keys match the pattern."""
    deleted = await svc.flush_pattern(svc.make_key("rag", "*"))
    assert deleted == 0


@pytest.mark.asyncio
async def test_overwrite_existing_key(svc: CacheService):
    """set() on an existing key overwrites the previous value."""
    key = svc.make_key("embedding", "abc123")
    await svc.set(key, json.dumps([0.1, 0.2]), ttl=86400)
    await svc.set(key, json.dumps([0.9, 0.8]), ttl=86400)
    result = await svc.get(key)
    assert json.loads(result) == [0.9, 0.8]


@pytest.mark.asyncio
async def test_corrupt_json_is_deleted_and_returns_none(svc: CacheService):
    """get() deletes a corrupt JSON entry and returns None. (Requirement 1.1)"""
    key = svc.make_key("protocol", "corrupt")
    # Bypass CacheService.set() to inject corrupt data directly
    await svc._client.set(key, "not-valid-json{{{{")
    result = await svc.get(key)
    assert result is None
    # Key must have been cleaned up
    assert await svc._client.get(key) is None


# ---------------------------------------------------------------------------
# 2. Key versioning — changing CACHE_KEY_VERSION isolates entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_key_versioning_isolates_entries():
    """
    Entries written under v1 are invisible under v2 and vice-versa.
    Changing CACHE_KEY_VERSION effectively invalidates all stale entries.
    (Requirement 9.3)
    """
    shared_redis = fakeredis.FakeAsyncRedis(decode_responses=True)

    svc_v1 = CacheService(_make_settings(CACHE_KEY_VERSION="v1"))
    svc_v1._client = shared_redis
    svc_v1._degraded = False

    svc_v2 = CacheService(_make_settings(CACHE_KEY_VERSION="v2"))
    svc_v2._client = shared_redis
    svc_v2._degraded = False

    key_v1 = svc_v1.make_key("protocol", "amoxicillin")
    key_v2 = svc_v2.make_key("protocol", "amoxicillin")

    assert key_v1 == "v1:protocol:amoxicillin"
    assert key_v2 == "v2:protocol:amoxicillin"

    await svc_v1.set(key_v1, '{"version": "v1"}', ttl=3600)

    # v2 service must not see the v1 entry
    assert await svc_v2.get(key_v2) is None

    # v1 service still sees its own entry
    assert await svc_v1.get(key_v1) is not None

    await shared_redis.aclose()


@pytest.mark.asyncio
async def test_key_version_prefix_format():
    """make_key always produces <version>:<domain>:<identifier>. (Requirement 9.3)"""
    for version in ("v1", "v2", "v99"):
        svc = CacheService(_make_settings(CACHE_KEY_VERSION=version))
        assert svc.make_key("rag", "abc") == f"{version}:rag:abc"
        assert svc.make_key("protocol", "amox") == f"{version}:protocol:amox"


# ---------------------------------------------------------------------------
# 3. Degraded mode recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_degraded_mode_get_returns_none(svc: CacheService):
    """In degraded mode get() returns None without touching Redis. (Requirement 1.4)"""
    svc._degraded = True
    # Even if a key exists in Redis, degraded mode must bypass it
    await svc._client.set(svc.make_key("protocol", "test"), '{"x": 1}')
    result = await svc.get(svc.make_key("protocol", "test"))
    assert result is None


@pytest.mark.asyncio
async def test_degraded_mode_set_is_noop(svc: CacheService):
    """In degraded mode set() is a no-op — nothing is written to Redis. (Requirement 1.4)"""
    svc._degraded = True
    key = svc.make_key("embedding", "deadbeef")
    await svc.set(key, "[1.0, 2.0]", ttl=86400)
    # Directly check Redis — key must not exist
    assert await svc._client.get(key) is None


@pytest.mark.asyncio
async def test_degraded_mode_delete_is_noop(svc: CacheService):
    """In degraded mode delete() is a no-op. (Requirement 1.4)"""
    key = svc.make_key("protocol", "amox")
    await svc._client.set(key, '{}')  # write directly
    svc._degraded = True
    await svc.delete(key)
    # Key must still exist because delete was a no-op
    assert await svc._client.get(key) is not None


@pytest.mark.asyncio
async def test_degraded_mode_flush_pattern_returns_zero(svc: CacheService):
    """In degraded mode flush_pattern() returns 0. (Requirement 1.4)"""
    await svc._client.set(svc.make_key("rag", "h1"), '{}')
    svc._degraded = True
    deleted = await svc.flush_pattern(svc.make_key("rag", "*"))
    assert deleted == 0


@pytest.mark.asyncio
async def test_degraded_mode_recovery_via_ping(svc: CacheService):
    """
    ping() clears degraded mode when Redis is reachable again.
    (Requirement 1.6)
    """
    # Simulate degraded mode
    svc._degraded = True
    cache_degraded.set(1)

    # ping() should succeed (fakeredis is healthy) and clear degraded flag
    result = await svc.ping()
    assert result is True
    assert svc.is_degraded is False
    assert cache_degraded._value.get() == 0.0


@pytest.mark.asyncio
async def test_redis_operation_error_enters_degraded_mode(svc: CacheService):
    """
    A Redis operation failure during normal operation enters degraded mode.
    (Requirement 1.6)
    """
    # Replace the client with one that raises on get
    broken_client = AsyncMock()
    broken_client.get.side_effect = ConnectionError("connection lost")
    svc._client = broken_client
    svc._degraded = False

    result = await svc.get(svc.make_key("protocol", "test"))
    assert result is None
    assert svc.is_degraded is True
    assert cache_degraded._value.get() == 1.0


@pytest.mark.asyncio
async def test_connect_failure_enters_degraded_mode():
    """
    connect() failure puts the service in degraded mode without raising.
    (Requirement 1.4)
    """
    svc = CacheService(_make_settings())
    mock_client = AsyncMock()
    mock_client.ping.side_effect = ConnectionError("Redis unreachable")
    with patch("backend.core.cache.aioredis.from_url", return_value=mock_client):
        await svc.connect()
    assert svc.is_degraded is True
    assert cache_degraded._value.get() == 1.0


@pytest.mark.asyncio
async def test_connect_success_clears_degraded_mode():
    """
    A successful connect() clears degraded mode and sets the gauge to 0.
    (Requirement 1.6)
    """
    svc = CacheService(_make_settings())
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    with patch("backend.core.cache.aioredis.from_url", return_value=fake):
        await svc.connect()
    assert svc.is_degraded is False
    assert cache_degraded._value.get() == 0.0
    await fake.aclose()


# ---------------------------------------------------------------------------
# 4. Warm-up with mocked MongoDB
# ---------------------------------------------------------------------------


def _make_protocol_doc(name: str) -> dict:
    """Return a minimal MongoDB document for an AntibioticProtocol."""
    return {
        "name": name,
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


def _make_interaction_doc(drug_a: str, drug_b: str, message: str) -> dict:
    return {"drug_a": drug_a, "drug_b": drug_b, "message": message}


@pytest.mark.asyncio
async def test_warmup_populates_protocol_cache(svc: CacheService):
    """
    load_protocols_from_db() writes each protocol to Redis under v1:protocol:<name>.
    (Requirement 10.1)
    """
    protocol_names = ["amoxicillin", "ceftriaxone"]
    docs = [_make_protocol_doc(n) for n in protocol_names]

    # Build a mock cursor that returns our docs
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=docs)

    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_cursor

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_db_module = MagicMock()
    mock_db_module.get_db.return_value = mock_db

    ps = PrescriptionService()

    with patch("backend.core.database.db", mock_db_module), \
         patch("backend.core.cache.cache_service", svc):
        await ps.load_protocols_from_db()

    for name in protocol_names:
        key = svc.make_key("protocol", name)
        raw = await svc.get(key)
        assert raw is not None, f"Expected protocol '{name}' in cache"
        restored = _doc_to_protocol(json.loads(raw))
        assert restored.name == name


@pytest.mark.asyncio
async def test_warmup_populates_interaction_cache(svc: CacheService):
    """
    load_interactions_from_db() writes the full interaction list to Redis
    under v1:drug_interactions:all. (Requirement 10.1)
    """
    interaction_docs = [
        _make_interaction_doc("ciprofloxacin", "warfarin", "QT prolongation risk"),
        _make_interaction_doc("gentamicin", "furosemide", "Nephrotoxic combination"),
    ]

    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=interaction_docs)

    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_cursor

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_db_module = MagicMock()
    mock_db_module.get_db.return_value = mock_db

    als = AlertService()

    with patch("backend.core.database.db", mock_db_module), \
         patch("backend.core.cache.cache_service", svc):
        await als.load_interactions_from_db()

    key = svc.make_key("drug_interactions", "all")
    raw = await svc.get(key)
    assert raw is not None
    cached_list = json.loads(raw)
    assert len(cached_list) == 2
    assert cached_list[0][0] == "ciprofloxacin"
    assert cached_list[1][0] == "gentamicin"


@pytest.mark.asyncio
async def test_warmup_fallback_when_mongodb_empty(svc: CacheService):
    """
    When MongoDB returns no documents, load_protocols_from_db() falls back to
    built-in protocols without writing to Redis. (Requirement 10.1)
    """
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])

    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_cursor

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_db_module = MagicMock()
    mock_db_module.get_db.return_value = mock_db

    ps = PrescriptionService()

    with patch("backend.core.database.db", mock_db_module), \
         patch("backend.core.cache.cache_service", svc):
        await ps.load_protocols_from_db()

    # In-process cache should be populated from built-in fallback
    assert len(ps._protocols_cache) == len(ANTIBIOTIC_PROTOCOLS)
    # Redis should have no protocol keys (nothing was written)
    deleted = await svc.flush_pattern(svc.make_key("protocol", "*"))
    assert deleted == 0


@pytest.mark.asyncio
async def test_warmup_fallback_when_mongodb_raises(svc: CacheService):
    """
    When MongoDB raises an exception, load_protocols_from_db() falls back to
    built-in protocols without crashing. (Requirement 10.1)
    """
    mock_db_module = MagicMock()
    mock_db_module.get_db.side_effect = RuntimeError("MongoDB unavailable")

    ps = PrescriptionService()

    with patch("backend.core.database.db", mock_db_module), \
         patch("backend.core.cache.cache_service", svc):
        await ps.load_protocols_from_db()  # must not raise

    assert len(ps._protocols_cache) == len(ANTIBIOTIC_PROTOCOLS)


@pytest.mark.asyncio
async def test_warmup_timeout_does_not_block_startup():
    """
    _warm_up_cache() aborts within 10 s when load_protocols_from_db() hangs.
    The application must not be blocked. (Requirement 10.1)
    """
    from backend.main import _warm_up_cache

    async def _slow_load():
        await asyncio.sleep(20)  # exceeds the 10 s timeout

    with patch("backend.main.prescription_service") as mock_ps, \
         patch("backend.main.alert_service"):
        mock_ps.load_protocols_from_db = _slow_load
        # Should complete well within 15 s (timeout is 10 s)
        await asyncio.wait_for(_warm_up_cache(), timeout=15)


@pytest.mark.asyncio
async def test_warmup_exception_does_not_block_startup(caplog):
    """
    _warm_up_cache() catches unexpected exceptions and logs them without
    propagating. (Requirement 10.1)
    """
    from backend.main import _warm_up_cache

    async def _failing_load():
        raise RuntimeError("Unexpected DB error")

    with patch("backend.main.prescription_service") as mock_ps, \
         patch("backend.main.alert_service"), \
         caplog.at_level(logging.ERROR, logger="backend.main"):
        mock_ps.load_protocols_from_db = _failing_load
        await _warm_up_cache()  # must not raise

    assert any("warm-up failed" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# 5. Protocol round-trip through fakeredis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protocol_round_trip_via_fakeredis(svc: CacheService):
    """
    Serialise an AntibioticProtocol to JSON, store in fakeredis, retrieve and
    deserialise — result must equal the original. (Requirements 1.1, 9.3)
    """
    protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
    key = svc.make_key("protocol", protocol.name)
    await svc.set(key, json.dumps(dataclasses.asdict(protocol)), ttl=3600)
    raw = await svc.get(key)
    assert raw is not None
    restored = _doc_to_protocol(json.loads(raw))
    assert restored == protocol


@pytest.mark.asyncio
async def test_interaction_round_trip_via_fakeredis(svc: CacheService):
    """
    Serialise the interaction list, store in fakeredis, retrieve and
    deserialise — result must equal the original. (Requirements 1.1, 9.3)
    """
    interactions = list(_DRUG_INTERACTIONS)
    key = svc.make_key("drug_interactions", "all")
    await svc.set(key, json.dumps(interactions), ttl=3600)
    raw = await svc.get(key)
    assert raw is not None
    restored = [tuple(item) for item in json.loads(raw)]
    assert restored == interactions
