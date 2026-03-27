"""
Property-based tests for auth cookie behaviour — Diagno-Pilot Security Hardening

Tests verify that JWT tokens are delivered exclusively via httpOnly cookies,
that cookie attributes are correct, and that cookie-based auth works end-to-end.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.core.config import settings
from backend.routers.auth import create_access_token, hash_password


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

role_strategy = st.sampled_from(["medecin", "admin", "infirmière", "guest"])

email_strategy = st.from_regex(r"[a-z]{3,8}@example\.com", fullmatch=True)

password_strategy = st.just("TestPassword123!")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_doc(role: str = "medecin", password: str = "TestPassword123!") -> dict:
    oid = ObjectId()
    return {
        "_id": oid,
        "email": "test@example.com",
        "password_hash": hash_password(password),
        "role": role,
        "full_name": "Dr. Test",
        "locale": "fr",
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
    }


def _make_refresh_token_doc(token_value: str, user_id: str, days_offset: int = 7) -> dict:
    expires_at = datetime.now(timezone.utc) + timedelta(days=days_offset)
    return {
        "token": token_value,
        "user_id": user_id,
        "expires_at": expires_at,
        "revoked": False,
    }


def _parse_set_cookie(headers, name: str) -> dict:
    """Parse a Set-Cookie header for a given cookie name into a dict of attributes."""
    for value in headers.get_list("set-cookie"):
        parts = [p.strip() for p in value.split(";")]
        cookie_name, cookie_val = parts[0].split("=", 1)
        if cookie_name.strip() == name:
            attrs = {"value": cookie_val}
            for part in parts[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    attrs[k.strip().lower()] = v.strip()
                else:
                    attrs[part.strip().lower()] = True
            return attrs
    return {}


def _make_mock_db(user_doc: dict, token_doc: dict | None = None):
    """Build a mock DB that returns the given user and optional token doc."""
    mock_rt_collection = MagicMock()
    mock_rt_collection.find_one = AsyncMock(return_value=token_doc)
    mock_rt_collection.update_one = AsyncMock(return_value=None)
    mock_rt_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="rt_id"))

    mock_users_collection = MagicMock()
    mock_users_collection.find_one = AsyncMock(return_value=user_doc)
    mock_users_collection.update_one = AsyncMock(return_value=None)

    def get_collection(name: str):
        if name == "refresh_tokens":
            return mock_rt_collection
        return mock_users_collection

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(side_effect=get_collection)
    return mock_db, mock_rt_collection


def _make_audit_mock_db():
    audit_collection = MagicMock()
    audit_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_id"))
    audit_mock_db = MagicMock()
    audit_mock_db.__getitem__ = MagicMock(return_value=audit_collection)
    return audit_mock_db


# ---------------------------------------------------------------------------
# Property 1 — Login sets all auth cookies with correct attributes
# Feature: security-hardening, Property 1: Login sets all auth cookies with correct attributes
# Validates: Requirements 1.1, 1.2, 6.1
# ---------------------------------------------------------------------------

@h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(role=role_strategy)
@pytest.mark.asyncio
async def test_p1_login_sets_all_auth_cookies_with_correct_attributes(role: str):
    """
    # Feature: security-hardening, Property 1: Login sets all auth cookies with correct attributes
    # Validates: Requirements 1.1, 1.2, 6.1

    For any valid user credentials, a successful POST /api/v1/auth/login response
    must set all three cookies — access_token (HttpOnly), refresh_token (HttpOnly),
    and csrf_token (not HttpOnly) — each with SameSite=Strict and correct Max-Age.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    user_doc = _make_user_doc(role=role)
    mock_db, _ = _make_mock_db(user_doc)
    audit_mock_db = _make_audit_mock_db()

    with patch("backend.routers.auth.db") as mock_db_obj, \
         patch("backend.core.auth.db") as mock_core_db_obj, \
         patch("backend.services.audit_service.db") as mock_audit_db_obj:
        mock_db_obj.get_db.return_value = mock_db
        mock_core_db_obj.get_db.return_value = mock_db
        mock_audit_db_obj.get_db.return_value = audit_mock_db

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/login",
                data={"username": "test@example.com", "password": "TestPassword123!"},
            )

    assert resp.status_code == 200

    # access_token cookie — must be HttpOnly
    at = _parse_set_cookie(resp.headers, "access_token")
    assert at, "access_token cookie not found in Set-Cookie headers"
    assert at.get("value"), "access_token cookie value is empty"
    assert "httponly" in at, "access_token must be HttpOnly"
    assert at.get("samesite", "").lower() == "strict", "access_token must have SameSite=Strict"
    expected_at_max_age = str(settings.JWT_EXPIRE_MINUTES * 60)
    assert at.get("max-age") == expected_at_max_age, (
        f"access_token Max-Age should be {expected_at_max_age}, got {at.get('max-age')}"
    )

    # refresh_token cookie — must be HttpOnly
    rt = _parse_set_cookie(resp.headers, "refresh_token")
    assert rt, "refresh_token cookie not found in Set-Cookie headers"
    assert rt.get("value"), "refresh_token cookie value is empty"
    assert "httponly" in rt, "refresh_token must be HttpOnly"
    assert rt.get("samesite", "").lower() == "strict", "refresh_token must have SameSite=Strict"
    expected_rt_max_age = str(settings.JWT_REFRESH_EXPIRE_DAYS * 86400)
    assert rt.get("max-age") == expected_rt_max_age, (
        f"refresh_token Max-Age should be {expected_rt_max_age}, got {rt.get('max-age')}"
    )

    # csrf_token cookie — must NOT be HttpOnly
    ct = _parse_set_cookie(resp.headers, "csrf_token")
    assert ct, "csrf_token cookie not found in Set-Cookie headers"
    assert ct.get("value"), "csrf_token cookie value is empty"
    assert "httponly" not in ct, "csrf_token must NOT be HttpOnly"
    assert ct.get("samesite", "").lower() == "strict", "csrf_token must have SameSite=Strict"
    assert ct.get("max-age") == expected_rt_max_age, (
        f"csrf_token Max-Age should be {expected_rt_max_age}, got {ct.get('max-age')}"
    )


# ---------------------------------------------------------------------------
# Property 2 — Tokens absent from login response body
# Feature: security-hardening, Property 2: Tokens absent from login response body
# Validates: Requirements 1.3
# ---------------------------------------------------------------------------

@h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(role=role_strategy)
@pytest.mark.asyncio
async def test_p2_tokens_absent_from_login_response_body(role: str):
    """
    # Feature: security-hardening, Property 2: Tokens absent from login response body
    # Validates: Requirements 1.3

    For any successful login response, the JSON body must not contain the keys
    access_token or refresh_token.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    user_doc = _make_user_doc(role=role)
    mock_db, _ = _make_mock_db(user_doc)
    audit_mock_db = _make_audit_mock_db()

    with patch("backend.routers.auth.db") as mock_db_obj, \
         patch("backend.core.auth.db") as mock_core_db_obj, \
         patch("backend.services.audit_service.db") as mock_audit_db_obj:
        mock_db_obj.get_db.return_value = mock_db
        mock_core_db_obj.get_db.return_value = mock_db
        mock_audit_db_obj.get_db.return_value = audit_mock_db

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/login",
                data={"username": "test@example.com", "password": "TestPassword123!"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" not in body, "access_token must not appear in login response body"
    assert "refresh_token" not in body, "refresh_token must not appear in login response body"
    assert body.get("token_type") == "bearer"
    assert "expires_in" in body


# ---------------------------------------------------------------------------
# Property 3 — Cookie-based auth grants access to protected endpoints
# Feature: security-hardening, Property 3: Cookie-based auth grants access to protected endpoints
# Validates: Requirements 1.4
# ---------------------------------------------------------------------------

@h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(role=role_strategy)
@pytest.mark.asyncio
async def test_p3_cookie_based_auth_grants_access_to_protected_endpoints(role: str):
    """
    # Feature: security-hardening, Property 3: Cookie-based auth grants access to protected endpoints
    # Validates: Requirements 1.4

    For any valid access_token cookie value, a request to a protected endpoint
    that carries the cookie but no Authorization: Bearer header must receive a
    non-401 response.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    user_doc = _make_user_doc(role=role)
    user_id = str(user_doc["_id"])
    access_token = create_access_token(user_id=user_id, role=role)

    mock_db, _ = _make_mock_db(user_doc)

    with patch("backend.routers.auth.db") as mock_db_obj, \
         patch("backend.core.auth.db") as mock_core_db_obj:
        mock_db_obj.get_db.return_value = mock_db
        mock_core_db_obj.get_db.return_value = mock_db

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # No Authorization header — only cookie
            client.cookies.set("access_token", access_token)
            resp = await client.get(
                "/api/v1/auth/me",
            )

    assert resp.status_code != 401, (
        f"Cookie-based auth should grant access, got {resp.status_code}: {resp.text}"
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Property 4 — Logout clears all auth cookies
# Feature: security-hardening, Property 4: Logout clears all auth cookies
# Validates: Requirements 1.5, 6.6
# ---------------------------------------------------------------------------

@h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(role=role_strategy)
@pytest.mark.asyncio
async def test_p4_logout_clears_all_auth_cookies(role: str):
    """
    # Feature: security-hardening, Property 4: Logout clears all auth cookies
    # Validates: Requirements 1.5, 6.6

    For any authenticated session, a POST /api/v1/auth/logout response must set
    access_token, refresh_token, and csrf_token cookies with Max-Age=0.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    user_doc = _make_user_doc(role=role)
    user_id = str(user_doc["_id"])
    access_token = create_access_token(user_id=user_id, role=role)

    mock_db, _ = _make_mock_db(user_doc)
    audit_mock_db = _make_audit_mock_db()

    with patch("backend.routers.auth.db") as mock_db_obj, \
         patch("backend.core.auth.db") as mock_core_db_obj, \
         patch("backend.services.audit_service.db") as mock_audit_db_obj:
        mock_db_obj.get_db.return_value = mock_db
        mock_core_db_obj.get_db.return_value = mock_db
        mock_audit_db_obj.get_db.return_value = audit_mock_db

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.cookies.set("access_token", access_token)
            resp = await client.post(
                "/api/v1/auth/logout",
            )

    assert resp.status_code == 200

    # All three cookies must be cleared (Max-Age=0)
    for cookie_name in ("access_token", "refresh_token", "csrf_token"):
        cookie = _parse_set_cookie(resp.headers, cookie_name)
        assert cookie, f"{cookie_name} cookie not found in logout Set-Cookie headers"
        assert cookie.get("max-age") == "0", (
            f"{cookie_name} must have Max-Age=0 on logout, got {cookie.get('max-age')}"
        )


# ---------------------------------------------------------------------------
# Property 5 — Refresh rotates all three cookies atomically
# Feature: security-hardening, Property 5: Refresh rotates all three cookies atomically
# Validates: Requirements 1.6, 2.1, 7.1
# ---------------------------------------------------------------------------

@h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(
    token_suffix=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-",
        min_size=4,
        max_size=32,
    )
)
@pytest.mark.asyncio
async def test_p5_refresh_rotates_all_three_cookies_atomically(token_suffix: str):
    """
    # Feature: security-hardening, Property 5: Refresh rotates all three cookies atomically
    # Validates: Requirements 1.6, 2.1, 7.1

    For any valid refresh_token cookie, a POST /api/v1/auth/refresh response must
    set new access_token, refresh_token, and csrf_token cookies in a single response,
    and the old refresh token must be revoked (a second call with the same token
    must return 401).
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    old_token_value = f"old-token-{token_suffix}"
    user_doc = _make_user_doc()
    user_id = str(user_doc["_id"])

    # Stateful in-memory store simulating MongoDB rotation
    token_store: dict[str, dict] = {
        old_token_value: _make_refresh_token_doc(old_token_value, user_id),
    }

    async def fake_find_one(query: dict) -> dict | None:
        token_val = query.get("token")
        if token_val is None:
            return None
        doc = token_store.get(token_val)
        return dict(doc) if doc else None

    async def fake_update_one(filter_: dict, update: dict) -> None:
        token_val = filter_.get("token")
        if token_val and token_val in token_store:
            token_store[token_val].update(update.get("$set", {}))

    async def fake_insert_one(doc: dict):
        token_store[doc["token"]] = dict(doc)
        return MagicMock(inserted_id="new_rt_id")

    mock_rt_collection = MagicMock()
    mock_rt_collection.find_one = AsyncMock(side_effect=fake_find_one)
    mock_rt_collection.update_one = AsyncMock(side_effect=fake_update_one)
    mock_rt_collection.insert_one = AsyncMock(side_effect=fake_insert_one)

    mock_users_collection = MagicMock()
    mock_users_collection.find_one = AsyncMock(return_value=user_doc)

    def get_collection(name: str):
        if name == "refresh_tokens":
            return mock_rt_collection
        return mock_users_collection

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(side_effect=get_collection)

    with patch("backend.routers.auth.db") as mock_db_obj:
        mock_db_obj.get_db.return_value = mock_db

        # First refresh — must succeed and set all three cookies
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.cookies.set("refresh_token", old_token_value)
            first_resp = await client.post(
                "/api/v1/auth/refresh",
            )
        assert first_resp.status_code == 200, (
            f"Expected 200 on first refresh, got {first_resp.status_code}: {first_resp.text}"
        )

        # All three cookies must be set in the single response
        for cookie_name in ("access_token", "refresh_token", "csrf_token"):
            cookie = _parse_set_cookie(first_resp.headers, cookie_name)
            assert cookie, f"{cookie_name} cookie not found in refresh response"
            assert cookie.get("value"), f"{cookie_name} cookie value is empty after refresh"

        # Second use of the same old token — must be rejected (rotation)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client2:
            client2.cookies.set("refresh_token", old_token_value)
            second_resp = await client2.post(
                "/api/v1/auth/refresh",
            )
        assert second_resp.status_code == 401, (
            f"Expected 401 on second use of old token, got {second_resp.status_code}"
        )
        assert second_resp.json().get("detail") == "refresh_token_invalid"


# ---------------------------------------------------------------------------
# Property 6 — Invalid refresh token returns 401 and clears cookies
# Feature: security-hardening, Property 6: Invalid refresh token returns 401 and clears cookies
# Validates: Requirements 2.2
# ---------------------------------------------------------------------------

invalid_token_strategy = st.one_of(
    st.just(""),                          # absent / empty
    st.just("revoked-token-value"),       # revoked
    st.just("expired-token-value"),       # expired
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=64),  # random garbage
)


@h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(invalid_token=invalid_token_strategy)
@pytest.mark.asyncio
async def test_p6_invalid_refresh_token_returns_401_and_clears_cookies(invalid_token: str):
    """
    # Feature: security-hardening, Property 6: Invalid refresh token returns 401 and clears cookies
    # Validates: Requirements 2.2

    For any absent, revoked, or expired refresh_token cookie value,
    POST /api/v1/auth/refresh must return HTTP 401 with detail "refresh_token_invalid"
    and set all auth cookies to Max-Age=0.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    # All tokens are unknown/invalid — DB returns None
    mock_rt_collection = MagicMock()
    mock_rt_collection.find_one = AsyncMock(return_value=None)

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_rt_collection)

    with patch("backend.routers.auth.db") as mock_db_obj:
        mock_db_obj.get_db.return_value = mock_db

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            if invalid_token:
                client.cookies.set("refresh_token", invalid_token)
                resp = await client.post(
                    "/api/v1/auth/refresh",
                )
            else:
                # No cookie at all
                resp = await client.post("/api/v1/auth/refresh")

    assert resp.status_code == 401, (
        f"Expected 401 for invalid token, got {resp.status_code}: {resp.text}"
    )
    assert resp.json().get("detail") == "refresh_token_invalid"

    # All three cookies must be cleared (Max-Age=0)
    for cookie_name in ("access_token", "refresh_token", "csrf_token"):
        cookie = _parse_set_cookie(resp.headers, cookie_name)
        assert cookie, f"{cookie_name} cookie not found in 401 response Set-Cookie headers"
        assert cookie.get("max-age") == "0", (
            f"{cookie_name} must have Max-Age=0 on invalid refresh, got {cookie.get('max-age')}"
        )
