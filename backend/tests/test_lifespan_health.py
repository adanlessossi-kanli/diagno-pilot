"""
Unit tests for lifespan CacheService wiring and /health endpoint — Diagno-Pilot

Subtask 10.1: Write unit tests for lifespan and health endpoint
**Validates: Requirements 1.5, 10.5, 10.6**

Tests:
- /health response includes `redis` field with "ok" or "degraded"
- /health overall status is "degraded" when Redis is unhealthy
- warm-up timeout: mock load_protocols_from_db to sleep > 10 s; assert warm-up exits
  without blocking the application
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# /health endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_includes_redis_ok_field():
    """
    /health response must include a `redis` field set to "ok" when Redis is reachable.
    Validates: Requirements 1.5, 10.5
    """
    from backend.main import app

    mock_cache = MagicMock()
    mock_cache.ping = AsyncMock(return_value=True)

    mock_db = MagicMock()
    mock_db.get_db.return_value.client.admin.command = AsyncMock(return_value={"ok": 1})

    with patch("backend.main.cache_service", mock_cache), \
         patch("backend.main.db", mock_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert "redis" in body
    assert body["redis"] == "ok"
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_health_redis_degraded_when_ping_fails():
    """
    /health response must include `redis: "degraded"` and overall `status: "degraded"`
    when cache_service.ping() returns False.
    Validates: Requirements 1.5
    """
    from backend.main import app

    mock_cache = MagicMock()
    mock_cache.ping = AsyncMock(return_value=False)

    mock_db = MagicMock()
    mock_db.get_db.return_value.client.admin.command = AsyncMock(return_value={"ok": 1})

    with patch("backend.main.cache_service", mock_cache), \
         patch("backend.main.db", mock_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["redis"] == "degraded"
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_status_degraded_when_db_unreachable():
    """
    /health overall status is "degraded" when MongoDB is unreachable, even if Redis is ok.
    Validates: Requirements 1.5
    """
    from backend.main import app

    mock_cache = MagicMock()
    mock_cache.ping = AsyncMock(return_value=True)

    mock_db = MagicMock()
    mock_db.get_db.return_value.client.admin.command = AsyncMock(
        side_effect=Exception("MongoDB unreachable")
    )

    with patch("backend.main.cache_service", mock_cache), \
         patch("backend.main.db", mock_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["redis"] == "ok"
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_both_degraded():
    """
    /health overall status is "degraded" when both MongoDB and Redis are unhealthy.
    Validates: Requirements 1.5
    """
    from backend.main import app

    mock_cache = MagicMock()
    mock_cache.ping = AsyncMock(return_value=False)

    mock_db = MagicMock()
    mock_db.get_db.return_value.client.admin.command = AsyncMock(
        side_effect=Exception("MongoDB unreachable")
    )

    with patch("backend.main.cache_service", mock_cache), \
         patch("backend.main.db", mock_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["redis"] == "degraded"
    assert body["db"].startswith("unreachable")
    assert body["status"] == "degraded"


# ---------------------------------------------------------------------------
# Warm-up timeout tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_warm_up_exits_on_timeout():
    """
    _warm_up_cache() must exit within the 10-second timeout even when
    load_protocols_from_db sleeps longer than 10 seconds.
    The warm-up must not block the application.
    Validates: Requirements 10.5, 10.6
    """
    from backend.main import _warm_up_cache

    async def slow_load():
        await asyncio.sleep(20)  # longer than the 10 s timeout

    with patch("backend.main.prescription_service") as mock_ps, \
         patch("backend.main.alert_service"):
        mock_ps.load_protocols_from_db = slow_load

        # _warm_up_cache must complete (not hang) despite the slow load
        # We use asyncio.wait_for with a generous 12 s budget to confirm it exits
        try:
            await asyncio.wait_for(_warm_up_cache(), timeout=12)
        except asyncio.TimeoutError:
            pytest.fail(
                "_warm_up_cache() did not exit within 12 s — it is blocking the application"
            )


@pytest.mark.asyncio
async def test_warm_up_exits_on_exception():
    """
    _warm_up_cache() must catch unexpected exceptions and return without raising.
    Validates: Requirements 10.4
    """
    from backend.main import _warm_up_cache

    async def failing_load():
        raise RuntimeError("DB connection lost")

    with patch("backend.main.prescription_service") as mock_ps, \
         patch("backend.main.alert_service"):
        mock_ps.load_protocols_from_db = failing_load

        # Must not raise
        await _warm_up_cache()


@pytest.mark.asyncio
async def test_warm_up_completes_normally():
    """
    _warm_up_cache() completes without error when both services load successfully.
    Validates: Requirements 10.1, 10.2, 10.3
    """
    from backend.main import _warm_up_cache

    with patch("backend.main.prescription_service") as mock_ps, \
         patch("backend.main.alert_service") as mock_as:
        mock_ps.load_protocols_from_db = AsyncMock()
        mock_as.load_interactions_from_db = AsyncMock()

        await _warm_up_cache()

        mock_ps.load_protocols_from_db.assert_called_once()
        mock_as.load_interactions_from_db.assert_called_once()
