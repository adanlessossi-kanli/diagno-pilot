"""
Property-based tests for CSRF middleware — Diagno-Pilot Security Hardening

Tests verify that the CSRF double-submit-cookie middleware correctly enforces
token validation on all state-mutating endpoints.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from backend.routers.auth import _generate_csrf_token, hash_password
from datetime import datetime, timezone
from bson import ObjectId


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# State-mutating HTTP methods that must be CSRF-protected
mutating_method_strategy = st.sampled_from(["POST", "PUT", "PATCH", "DELETE"])

# Paths that are NOT exempt from CSRF (any path other than the two exempt ones)
non_exempt_path_strategy = st.sampled_from([
    "/api/v1/patients",
    "/api/v1/files/upload",
    "/api/v1/chat",
    "/api/v1/diagnose",
    "/api/v1/documents",
    "/api/v1/alerts",
    "/api/v1/admin/users",
])

# Token value strategy — printable ASCII, no semicolons (cookie-safe)
token_value_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=8,
    max_size=64,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_doc(role: str = "medecin") -> dict:
    oid = ObjectId()
    return {
        "_id": oid,
        "email": "test@example.com",
        "password_hash": hash_password("TestPassword123!"),
        "role": role,
        "full_name": "Dr. Test",
        "locale": "fr",
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
    }


def _make_mock_db(user_doc: dict):
    mock_users_collection = MagicMock()
    mock_users_collection.find_one = AsyncMock(return_value=user_doc)
    mock_users_collection.update_one = AsyncMock(return_value=None)

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_users_collection)
    return mock_db


# ---------------------------------------------------------------------------
# Property 11 — CSRF middleware enforces token on all state-mutating endpoints
# Feature: security-hardening, Property 11: CSRF middleware enforces token on all state-mutating endpoints
# Validates: Requirements 6.3, 6.4, 6.5
# ---------------------------------------------------------------------------

@h_settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(
    cookie_token=token_value_strategy,
    header_token=token_value_strategy,
)
@pytest.mark.asyncio
async def test_p11_csrf_middleware_enforces_token_on_state_mutating_endpoints(
    cookie_token: str,
    header_token: str,
):
    """
    # Feature: security-hardening, Property 11: CSRF middleware enforces token on all state-mutating endpoints
    # Validates: Requirements 6.3, 6.4, 6.5

    For any POST/PUT/PATCH/DELETE request to a non-exempt endpoint:
    - If X-CSRF-Token header does not match csrf_token cookie → HTTP 403 with detail "csrf_token_invalid"
    - If X-CSRF-Token header matches csrf_token cookie → NOT rejected with 403 for CSRF reasons
    """
    from httpx import AsyncClient, ASGITransport
    from backend.core.csrf import verify_csrf
    from fastapi import FastAPI

    # Build a minimal test app with the CSRF dependency applied globally
    test_app = FastAPI()
    test_app.router.dependencies.append(__import__("fastapi", fromlist=["Depends"]).Depends(verify_csrf))

    @test_app.post("/api/v1/test-endpoint")
    async def test_endpoint():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        # --- Mismatched tokens → must get 403 ---
        if cookie_token != header_token:
            client.cookies.set("csrf_token", cookie_token)
            resp_mismatch = await client.post(
                "/api/v1/test-endpoint",
                headers={"X-CSRF-Token": header_token},
            )
            assert resp_mismatch.status_code == 403, (
                f"Expected 403 for mismatched CSRF tokens, got {resp_mismatch.status_code}"
            )
            assert resp_mismatch.json().get("detail") == "csrf_token_invalid", (
                f"Expected detail 'csrf_token_invalid', got {resp_mismatch.json()}"
            )

        # --- Matching tokens → must NOT be rejected with 403 ---
        client.cookies.set("csrf_token", cookie_token)
        resp_match = await client.post(
            "/api/v1/test-endpoint",
            headers={"X-CSRF-Token": cookie_token},
        )
        assert resp_match.status_code != 403, (
            f"Matching CSRF tokens should not be rejected, got {resp_match.status_code}"
        )
        assert resp_match.status_code == 200


@h_settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(cookie_token=token_value_strategy)
@pytest.mark.asyncio
async def test_p11_csrf_missing_header_returns_403(cookie_token: str):
    """
    # Feature: security-hardening, Property 11: CSRF middleware enforces token on all state-mutating endpoints
    # Validates: Requirements 6.3, 6.4, 6.5

    When X-CSRF-Token header is absent, the middleware must return 403.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.core.csrf import verify_csrf
    from fastapi import FastAPI
    import fastapi

    test_app = FastAPI()
    test_app.router.dependencies.append(fastapi.Depends(verify_csrf))

    @test_app.post("/api/v1/test-endpoint")
    async def test_endpoint():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        client.cookies.set("csrf_token", cookie_token)
        resp = await client.post(
            "/api/v1/test-endpoint",
            # No X-CSRF-Token header
        )
        assert resp.status_code == 403
        assert resp.json().get("detail") == "csrf_token_invalid"


@h_settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(header_token=token_value_strategy)
@pytest.mark.asyncio
async def test_p11_csrf_missing_cookie_returns_403(header_token: str):
    """
    # Feature: security-hardening, Property 11: CSRF middleware enforces token on all state-mutating endpoints
    # Validates: Requirements 6.3, 6.4, 6.5

    When csrf_token cookie is absent, the middleware must return 403.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.core.csrf import verify_csrf
    from fastapi import FastAPI
    import fastapi

    test_app = FastAPI()
    test_app.router.dependencies.append(fastapi.Depends(verify_csrf))

    @test_app.post("/api/v1/test-endpoint")
    async def test_endpoint():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/test-endpoint",
            headers={"X-CSRF-Token": header_token},
            # No csrf_token cookie
        )
        assert resp.status_code == 403
        assert resp.json().get("detail") == "csrf_token_invalid"


@pytest.mark.asyncio
async def test_p11_csrf_exempt_paths_skip_validation():
    """
    # Feature: security-hardening, Property 11: CSRF middleware enforces token on all state-mutating endpoints
    # Validates: Requirements 6.5

    POST /api/v1/auth/login and POST /api/v1/auth/refresh must be exempt from CSRF validation.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.core.csrf import verify_csrf
    from fastapi import FastAPI
    import fastapi

    test_app = FastAPI()
    test_app.router.dependencies.append(fastapi.Depends(verify_csrf))

    @test_app.post("/api/v1/auth/login")
    async def fake_login():
        return {"ok": True}

    @test_app.post("/api/v1/auth/refresh")
    async def fake_refresh():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        # No CSRF cookie or header — should still pass for exempt paths
        login_resp = await client.post("/api/v1/auth/login")
        assert login_resp.status_code == 200, (
            f"/api/v1/auth/login should be exempt from CSRF, got {login_resp.status_code}"
        )

        refresh_resp = await client.post("/api/v1/auth/refresh")
        assert refresh_resp.status_code == 200, (
            f"/api/v1/auth/refresh should be exempt from CSRF, got {refresh_resp.status_code}"
        )


@pytest.mark.asyncio
async def test_p11_csrf_get_requests_skip_validation():
    """
    # Feature: security-hardening, Property 11: CSRF middleware enforces token on all state-mutating endpoints
    # Validates: Requirements 6.3

    GET, HEAD, OPTIONS requests must not require CSRF validation.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.core.csrf import verify_csrf
    from fastapi import FastAPI
    import fastapi

    test_app = FastAPI()
    test_app.router.dependencies.append(fastapi.Depends(verify_csrf))

    @test_app.get("/api/v1/patients")
    async def fake_get():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/v1/patients")
        assert resp.status_code == 200, (
            f"GET requests should not require CSRF, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Property 12 — CSRF token has sufficient entropy
# Feature: security-hardening, Property 12: CSRF token has sufficient entropy
# Validates: Requirements 7.3
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(n=st.integers(min_value=1, max_value=20))
def test_p12_csrf_token_has_sufficient_entropy(n: int):
    """
    # Feature: security-hardening, Property 12: CSRF token has sufficient entropy
    # Validates: Requirements 7.3

    For any N tokens generated by _generate_csrf_token(), all must have length >= 64
    hex characters (representing >= 256 bits of entropy from secrets.token_hex(32)).
    """
    tokens = [_generate_csrf_token() for _ in range(n)]

    for token in tokens:
        assert len(token) >= 64, (
            f"CSRF token must be at least 64 hex chars (256 bits), got length {len(token)}: {token!r}"
        )
        # Verify it's valid hex
        assert all(c in "0123456789abcdef" for c in token), (
            f"CSRF token must be lowercase hex, got: {token!r}"
        )

    # All tokens must be unique (no collisions in a small batch)
    if n > 1:
        assert len(set(tokens)) == n, "CSRF tokens must be unique across generations"
