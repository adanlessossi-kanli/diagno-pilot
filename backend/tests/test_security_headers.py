"""
Property-based tests for security headers middleware — Diagno-Pilot Security Hardening

Tests verify that security-relevant HTTP response headers are present on all API
responses, and that HSTS is conditional on the production environment.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as h_settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A representative sample of registered API routes (GET endpoints that don't
# require complex setup) used to verify headers are present on all responses.
api_route_strategy = st.sampled_from([
    "/health",
    "/api/v1/auth/login",   # POST — will get 422 but headers still present
    "/api/v1/patients",     # GET — will get 401 but headers still present
    "/api/v1/auth/me",      # GET — will get 401 but headers still present
])

# Routes accessible via GET without auth (or that return a predictable status)
get_route_strategy = st.sampled_from([
    "/health",
    "/api/v1/patients",
    "/api/v1/auth/me",
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db():
    """Minimal mock DB that won't block startup-dependent routes."""
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.update_one = AsyncMock(return_value=None)
    mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="id"))

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    return mock_db


# ---------------------------------------------------------------------------
# Property 13 — Security headers present on all API responses
# Feature: security-hardening, Property 13: Security headers present on all API responses
# Validates: Requirements 8.1, 8.2, 8.4
# ---------------------------------------------------------------------------

@h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(route=get_route_strategy)
@pytest.mark.asyncio
async def test_p13_security_headers_present_on_all_api_responses_non_production(route: str):
    """
    # Feature: security-hardening, Property 13: Security headers present on all API responses
    # Validates: Requirements 8.1, 8.2, 8.4

    For any request to any endpoint under the FastAPI application, the response must
    contain X-Content-Type-Options: nosniff and X-Frame-Options: DENY.
    When settings.ENV != "production", HSTS must NOT be present.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    mock_db = _make_mock_db()

    with patch("backend.routers.auth.db") as mock_db_obj, \
         patch("backend.core.auth.db") as mock_core_db_obj, \
         patch("backend.core.security_headers.settings") as mock_settings:
        mock_db_obj.get_db.return_value = mock_db
        mock_core_db_obj.get_db.return_value = mock_db
        mock_settings.ENV = "development"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(route)

    # X-Content-Type-Options must always be present (Requirement 8.1)
    assert resp.headers.get("x-content-type-options") == "nosniff", (
        f"Expected X-Content-Type-Options: nosniff on {route}, "
        f"got: {resp.headers.get('x-content-type-options')!r}"
    )

    # X-Frame-Options must always be present (Requirement 8.2)
    assert resp.headers.get("x-frame-options") == "DENY", (
        f"Expected X-Frame-Options: DENY on {route}, "
        f"got: {resp.headers.get('x-frame-options')!r}"
    )

    # HSTS must NOT be present in non-production (Requirement 8.4)
    assert "strict-transport-security" not in resp.headers, (
        f"HSTS must not be present in non-production on {route}"
    )


@h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(route=get_route_strategy)
@pytest.mark.asyncio
async def test_p13_security_headers_present_on_all_api_responses_production(route: str):
    """
    # Feature: security-hardening, Property 13: Security headers present on all API responses
    # Validates: Requirements 8.1, 8.2, 8.4

    For any request to any endpoint under the FastAPI application, the response must
    contain X-Content-Type-Options: nosniff and X-Frame-Options: DENY.
    When settings.ENV == "production", HSTS must be present with the correct value.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    mock_db = _make_mock_db()

    with patch("backend.routers.auth.db") as mock_db_obj, \
         patch("backend.core.auth.db") as mock_core_db_obj, \
         patch("backend.core.security_headers.settings") as mock_settings:
        mock_db_obj.get_db.return_value = mock_db
        mock_core_db_obj.get_db.return_value = mock_db
        mock_settings.ENV = "production"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(route)

    # X-Content-Type-Options must always be present (Requirement 8.1)
    assert resp.headers.get("x-content-type-options") == "nosniff", (
        f"Expected X-Content-Type-Options: nosniff on {route} (production), "
        f"got: {resp.headers.get('x-content-type-options')!r}"
    )

    # X-Frame-Options must always be present (Requirement 8.2)
    assert resp.headers.get("x-frame-options") == "DENY", (
        f"Expected X-Frame-Options: DENY on {route} (production), "
        f"got: {resp.headers.get('x-frame-options')!r}"
    )

    # HSTS must be present in production (Requirement 8.4)
    hsts = resp.headers.get("strict-transport-security")
    assert hsts == "max-age=31536000; includeSubDomains", (
        f"Expected HSTS header on {route} (production), got: {hsts!r}"
    )


# ---------------------------------------------------------------------------
# Unit tests — SecurityHeadersMiddleware directly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_security_headers_middleware_non_production():
    """
    Unit test: HSTS absent in development, X-Content-Type-Options and X-Frame-Options present.
    """
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from backend.core.security_headers import SecurityHeadersMiddleware

    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    @test_app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    with patch("backend.core.security_headers.settings") as mock_settings:
        mock_settings.ENV = "development"
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/test")

    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "strict-transport-security" not in resp.headers


@pytest.mark.asyncio
async def test_security_headers_middleware_production():
    """
    Unit test: HSTS present in production with correct value.
    """
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from backend.core.security_headers import SecurityHeadersMiddleware

    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    @test_app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    with patch("backend.core.security_headers.settings") as mock_settings:
        mock_settings.ENV = "production"
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/test")

    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("strict-transport-security") == "max-age=31536000; includeSubDomains"


@pytest.mark.asyncio
async def test_security_headers_present_on_error_responses():
    """
    Unit test: Security headers are present even on error (4xx/5xx) responses.
    """
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from backend.core.security_headers import SecurityHeadersMiddleware

    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    @test_app.get("/not-found")
    async def not_found():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")

    with patch("backend.core.security_headers.settings") as mock_settings:
        mock_settings.ENV = "development"
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/not-found")

    assert resp.status_code == 404
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
