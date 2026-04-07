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

from backend.core.config import Settings

# Default CSP value used in tests
DEFAULT_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'"
)

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
        mock_settings.CSP_POLICY = DEFAULT_CSP

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

    # Content-Security-Policy must be present (Requirement 9.1)
    assert resp.headers.get("content-security-policy") == DEFAULT_CSP, (
        f"Expected CSP on {route}, got: {resp.headers.get('content-security-policy')!r}"
    )

    # Referrer-Policy must be present (Requirement 13.1)
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin", (
        f"Expected Referrer-Policy on {route}, got: {resp.headers.get('referrer-policy')!r}"
    )

    # Permissions-Policy must be present (Requirement 13.2)
    assert resp.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=(), payment=()", (
        f"Expected Permissions-Policy on {route}, got: {resp.headers.get('permissions-policy')!r}"
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
        mock_settings.CSP_POLICY = DEFAULT_CSP

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

    # Content-Security-Policy must be present (Requirement 9.1)
    assert resp.headers.get("content-security-policy") == DEFAULT_CSP, (
        f"Expected CSP on {route} (production), got: {resp.headers.get('content-security-policy')!r}"
    )

    # Referrer-Policy must be present (Requirement 13.1)
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin", (
        f"Expected Referrer-Policy on {route} (production), got: {resp.headers.get('referrer-policy')!r}"
    )

    # Permissions-Policy must be present (Requirement 13.2)
    assert resp.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=(), payment=()", (
        f"Expected Permissions-Policy on {route} (production), got: {resp.headers.get('permissions-policy')!r}"
    )


# ---------------------------------------------------------------------------
# Unit tests — SecurityHeadersMiddleware directly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_security_headers_middleware_non_production():
    """
    Unit test: HSTS absent in development, X-Content-Type-Options and X-Frame-Options present.
    CSP, Referrer-Policy, and Permissions-Policy present in all environments.
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
        mock_settings.CSP_POLICY = DEFAULT_CSP
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/test")

    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "strict-transport-security" not in resp.headers
    assert resp.headers.get("content-security-policy") == DEFAULT_CSP
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert resp.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=(), payment=()"


@pytest.mark.asyncio
async def test_security_headers_middleware_production():
    """
    Unit test: HSTS present in production with correct value.
    CSP, Referrer-Policy, and Permissions-Policy present in all environments.
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
        mock_settings.CSP_POLICY = DEFAULT_CSP
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/test")

    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("strict-transport-security") == "max-age=31536000; includeSubDomains"
    assert resp.headers.get("content-security-policy") == DEFAULT_CSP
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert resp.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=(), payment=()"


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
        mock_settings.CSP_POLICY = DEFAULT_CSP
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/not-found")

    assert resp.status_code == 404
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("content-security-policy") == DEFAULT_CSP
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert resp.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=(), payment=()"


# ---------------------------------------------------------------------------
# Property 1 — Complétude des en-têtes de sécurité (best-practices-hardening)
# Feature: best-practices-hardening, Property 1: Security headers completeness
# Validates: Requirements 9.1, 13.1, 13.2
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(path=st.from_regex(r"/[a-zA-Z0-9_/\-\.]{1,50}", fullmatch=True))
@pytest.mark.asyncio
async def test_p1_security_headers_completeness(path: str):
    """
    # Feature: best-practices-hardening, Property 1: Security headers completeness
    # Validates: Requirements 9.1, 13.1, 13.2

    For any request path, the response must contain Content-Security-Policy,
    Referrer-Policy, and Permissions-Policy with the expected values.
    """
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from backend.core.security_headers import SecurityHeadersMiddleware

    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    @test_app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def catch_all(full_path: str):
        return {"path": full_path}

    with patch("backend.core.security_headers.settings") as mock_settings:
        mock_settings.ENV = "development"
        mock_settings.CSP_POLICY = DEFAULT_CSP
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get(path)

    # Content-Security-Policy (Requirement 9.1)
    csp = resp.headers.get("content-security-policy")
    assert csp is not None, f"CSP header missing on path {path!r}"
    assert "default-src 'self'" in csp, f"CSP missing default-src 'self' on path {path!r}"

    # Referrer-Policy (Requirement 13.1)
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin", (
        f"Referrer-Policy incorrect on path {path!r}: {resp.headers.get('referrer-policy')!r}"
    )

    # Permissions-Policy (Requirement 13.2)
    assert resp.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=(), payment=()", (
        f"Permissions-Policy incorrect on path {path!r}: {resp.headers.get('permissions-policy')!r}"
    )


# ---------------------------------------------------------------------------
# Unit tests — ALLOWED_ORIGINS default and CSP configurable
# Feature: best-practices-hardening
# Validates: Requirements 8.1, 8.2, 9.2, 9.3
# ---------------------------------------------------------------------------

def test_allowed_origins_default_is_localhost():
    """
    Requirement 8.1: Default ALLOWED_ORIGINS must be http://localhost:3000.
    Verify the class-level default, isolated from .env file and environment variables.
    """
    import os
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None, ENV="development")
    assert s.ALLOWED_ORIGINS == "http://localhost:3000"


def test_allowed_origins_production_rejects_wildcard():
    """
    Requirement 8.2: Production validation must reject ALLOWED_ORIGINS='*'.
    """
    from pydantic import ValidationError
    with pytest.raises((ValidationError, ValueError)):
        Settings(
            ENV="production",
            ALLOWED_ORIGINS="*",
            JWT_SECRET="test_secret_long_enough_for_prod_32x",
            HIPAA_ENCRYPTION_KEY_ID="test-key-id",
            HIPAA_PHI_STRIP_ON_FALLBACK=True,
        )


@pytest.mark.asyncio
async def test_custom_csp_policy_used_in_header():
    """
    Requirements 9.2, 9.3: A custom CSP_POLICY value must be used in the response header.
    """
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from backend.core.security_headers import SecurityHeadersMiddleware

    custom_csp = "default-src 'none'; script-src 'self'"

    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    @test_app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    with patch("backend.core.security_headers.settings") as mock_settings:
        mock_settings.ENV = "development"
        mock_settings.CSP_POLICY = custom_csp
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/test")

    assert resp.headers.get("content-security-policy") == custom_csp, (
        f"Expected custom CSP {custom_csp!r}, got {resp.headers.get('content-security-policy')!r}"
    )
