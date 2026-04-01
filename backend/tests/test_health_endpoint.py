"""
Tests for the extended /health endpoint — LLM and embedding probes.

Feature: llm-resilience
Properties 8 and 9, plus unit tests for not_configured and concurrent execution.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Helpers / strategies
# ---------------------------------------------------------------------------

# Valid probe result values
_PROBE_VALUES = st.one_of(
    st.just("ok"),
    st.just("not_configured"),
    st.text(min_size=1, max_size=50).map(lambda s: f"unreachable: {s}"),
)

# Redis probe returns bool; we model redis_status as "ok" | "degraded"
_REDIS_VALUES = st.booleans()


def _expected_status(db: str, redis_ok: bool, llm_primary: str, llm_fallback: str, embedding: str) -> str:
    """Derive expected top-level status from component results."""
    return "ok" if (
        db == "ok" and redis_ok and llm_primary == "ok" and llm_fallback == "ok" and embedding == "ok"
    ) else "degraded"


def _make_mocks(db_result: str, redis_ok: bool, llm_primary: str, llm_fallback: str, embedding: str):
    """Return (mock_db, mock_cache, mock_primary, mock_fallback, mock_embed) patches."""
    mock_cache = MagicMock()
    mock_cache.ping = AsyncMock(return_value=redis_ok)

    if db_result == "ok":
        mock_db = MagicMock()
        mock_db.get_db.return_value.client.admin.command = AsyncMock(return_value={"ok": 1})
    else:
        reason = db_result.removeprefix("unreachable: ")
        mock_db = MagicMock()
        mock_db.get_db.return_value.client.admin.command = AsyncMock(
            side_effect=Exception(reason)
        )

    return mock_db, mock_cache


# ---------------------------------------------------------------------------
# Property 8: Health response structure and overall status derivation
# ---------------------------------------------------------------------------

# Feature: llm-resilience, Property 8: Health response structure and overall status derivation
@given(
    db_result=st.one_of(st.just("ok"), st.text(min_size=1, max_size=40).map(lambda s: f"unreachable: {s}")),
    redis_ok=_REDIS_VALUES,
    llm_primary=_PROBE_VALUES,
    llm_fallback=_PROBE_VALUES,
    embedding=_PROBE_VALUES,
)
@h_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_property8_health_response_structure_and_status_derivation(
    db_result, redis_ok, llm_primary, llm_fallback, embedding
):
    """
    Property 8: Health response structure and overall status derivation
    Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6

    For any combination of component probe results, the /health response SHALL
    contain all required component fields, and the top-level status SHALL be
    'ok' if and only if all four fields are 'ok'.
    """
    from backend.main import app

    mock_db, mock_cache = _make_mocks(db_result, redis_ok, llm_primary, llm_fallback, embedding)

    with (
        patch("backend.main.db", mock_db),
        patch("backend.main.cache_service", mock_cache),
        patch("backend.main._probe_llm_primary", AsyncMock(return_value=llm_primary)),
        patch("backend.main._probe_llm_fallback", AsyncMock(return_value=llm_fallback)),
        patch("backend.main._probe_embedding", AsyncMock(return_value=embedding)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    body = response.json()

    # All required fields must be present
    assert "status" in body
    assert "db" in body
    assert "redis" in body
    assert "llm_primary" in body
    assert "llm_fallback" in body
    assert "embedding" in body

    # Status derivation: "ok" iff all components are "ok"
    expected = _expected_status(db_result, redis_ok, llm_primary, llm_fallback, embedding)
    assert body["status"] == expected, (
        f"Expected status={expected!r} but got {body['status']!r} "
        f"for db={db_result!r}, redis_ok={redis_ok}, "
        f"llm_primary={llm_primary!r}, llm_fallback={llm_fallback!r}, embedding={embedding!r}"
    )


# ---------------------------------------------------------------------------
# Property 9: Health endpoint always returns HTTP 200
# ---------------------------------------------------------------------------

# Feature: llm-resilience, Property 9: Health endpoint always returns HTTP 200
@given(
    db_result=st.one_of(st.just("ok"), st.text(min_size=1, max_size=40).map(lambda s: f"unreachable: {s}")),
    redis_ok=_REDIS_VALUES,
    llm_primary=_PROBE_VALUES,
    llm_fallback=_PROBE_VALUES,
    embedding=_PROBE_VALUES,
)
@h_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_property9_health_always_returns_200(
    db_result, redis_ok, llm_primary, llm_fallback, embedding
):
    """
    Property 9: Health endpoint always returns HTTP 200
    Validates: Requirements 3.7

    For any combination of component probe results (including all failing),
    the /health endpoint SHALL return HTTP status code 200.
    """
    from backend.main import app

    mock_db, mock_cache = _make_mocks(db_result, redis_ok, llm_primary, llm_fallback, embedding)

    with (
        patch("backend.main.db", mock_db),
        patch("backend.main.cache_service", mock_cache),
        patch("backend.main._probe_llm_primary", AsyncMock(return_value=llm_primary)),
        patch("backend.main._probe_llm_fallback", AsyncMock(return_value=llm_fallback)),
        patch("backend.main._probe_embedding", AsyncMock(return_value=embedding)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200, (
        f"Expected HTTP 200 but got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Unit test 6.5: "not_configured" when URLs are absent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_primary_not_configured_when_url_absent():
    """
    When LLM_PRIMARY_URL is not set, llm_primary field must be 'not_configured'.
    Validates: Requirements 3.8
    """
    from backend.main import _probe_llm_primary

    with patch("backend.main.settings") as mock_settings:
        mock_settings.LLM_PRIMARY_URL = None
        result = await _probe_llm_primary()

    assert result == "not_configured"


@pytest.mark.asyncio
async def test_llm_fallback_not_configured_when_url_absent():
    """
    When LLM_FALLBACK_URL is not set, llm_fallback field must be 'not_configured'.
    Validates: Requirements 3.9
    """
    from backend.main import _probe_llm_fallback

    with patch("backend.main.settings") as mock_settings:
        mock_settings.LLM_FALLBACK_URL = None
        result = await _probe_llm_fallback()

    assert result == "not_configured"


@pytest.mark.asyncio
async def test_embedding_not_configured_when_url_absent():
    """
    When LLM_PRIMARY_URL is not set (embedding reuses it), embedding field must be 'not_configured'.
    Validates: Requirements 3.8
    """
    from backend.main import _probe_embedding

    with patch("backend.main.settings") as mock_settings:
        mock_settings.LLM_PRIMARY_URL = None
        result = await _probe_embedding()

    assert result == "not_configured"


@pytest.mark.asyncio
async def test_health_endpoint_not_configured_fields():
    """
    When both LLM URLs are absent, /health response includes 'not_configured' for
    llm_primary, llm_fallback, and embedding fields.
    Validates: Requirements 3.8, 3.9
    """
    from backend.main import app

    mock_cache = MagicMock()
    mock_cache.ping = AsyncMock(return_value=True)
    mock_db = MagicMock()
    mock_db.get_db.return_value.client.admin.command = AsyncMock(return_value={"ok": 1})

    with (
        patch("backend.main.db", mock_db),
        patch("backend.main.cache_service", mock_cache),
        patch("backend.main.settings") as mock_settings,
    ):
        mock_settings.LLM_PRIMARY_URL = None
        mock_settings.LLM_FALLBACK_URL = None
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    body = response.json()
    assert body["llm_primary"] == "not_configured"
    assert body["llm_fallback"] == "not_configured"
    assert body["embedding"] == "not_configured"
    # db and redis are ok, but not_configured != "ok" so overall is degraded
    assert body["status"] == "degraded"


# ---------------------------------------------------------------------------
# Unit test 6.6: Concurrent probe execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_probes_run_concurrently():
    """
    All probes must run concurrently via asyncio.gather.
    Total elapsed time should be approximately max(delays), not sum(delays).
    Validates: Requirements 3.10
    """
    from backend.main import app

    delay_db = 0.15
    delay_redis = 0.10
    delay_primary = 0.20
    delay_fallback = 0.12
    delay_embed = 0.18

    async def slow_mongo_probe():
        await asyncio.sleep(delay_db)
        return "ok"

    async def slow_redis_ping():
        await asyncio.sleep(delay_redis)
        return True

    async def slow_primary():
        await asyncio.sleep(delay_primary)
        return "ok"

    async def slow_fallback():
        await asyncio.sleep(delay_fallback)
        return "ok"

    async def slow_embed():
        await asyncio.sleep(delay_embed)
        return "ok"

    mock_db = MagicMock()
    mock_cache = MagicMock()
    mock_cache.ping = slow_redis_ping

    start = time.monotonic()
    with (
        patch("backend.main.db", mock_db),
        patch("backend.main.cache_service", mock_cache),
        patch("backend.main._probe_mongo", slow_mongo_probe),
        patch("backend.main._probe_llm_primary", slow_primary),
        patch("backend.main._probe_llm_fallback", slow_fallback),
        patch("backend.main._probe_embedding", slow_embed),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    elapsed = time.monotonic() - start
    max_delay = max(delay_db, delay_redis, delay_primary, delay_fallback, delay_embed)
    sum_delay = delay_db + delay_redis + delay_primary + delay_fallback + delay_embed

    assert response.status_code == 200
    # Elapsed should be close to max delay, not sum of delays
    # Allow generous overhead (0.5 s) for test infrastructure
    assert elapsed < max_delay + 0.5, (
        f"Probes appear sequential: elapsed={elapsed:.3f}s, max_delay={max_delay:.3f}s, "
        f"sum_delay={sum_delay:.3f}s"
    )
