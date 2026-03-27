"""
Tests unitaires pour l'authentification — Diagno-Pilot
Validates: Requirements REQ-01
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException
import jwt

from backend.core.config import settings
from backend.routers.auth import (
    create_access_token,
    hash_password,
    verify_password,
)


# ---------------------------------------------------------------------------
# 1. verify_password / hash_password
# ---------------------------------------------------------------------------

class TestPasswordHelpers:
    def test_hash_and_verify_roundtrip(self):
        plain = "SecretPass1!"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password("CorrectPassword")
        assert verify_password("WrongPassword", hashed) is False

    def test_empty_password_wrong(self):
        hashed = hash_password("SomePassword")
        assert verify_password("", hashed) is False

    def test_different_hashes_for_same_password(self):
        """bcrypt uses random salt — two hashes of the same password differ."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        assert verify_password("same", h1) is True
        assert verify_password("same", h2) is True


# ---------------------------------------------------------------------------
# 2. create_access_token
# ---------------------------------------------------------------------------

class TestCreateAccessToken:
    def test_token_decodes_with_correct_user_id_and_role(self):
        user_id = str(ObjectId())
        role = "medecin"
        token = create_access_token(user_id=user_id, role=role)
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert payload["sub"] == user_id
        assert payload["role"] == role

    def test_token_has_expiry(self):
        token = create_access_token(user_id="abc123", role="admin")
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert "exp" in payload

    def test_token_expiry_is_in_future(self):
        token = create_access_token(user_id="abc123", role="admin")
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers for endpoint tests
# ---------------------------------------------------------------------------

# Pre-compute a bcrypt hash once at module load to avoid hashing on every
# Hypothesis example (bcrypt is intentionally slow — 100 hashes ≈ 10 s).
_DEFAULT_PASSWORD = "password123"
_DEFAULT_PASSWORD_HASH = hash_password(_DEFAULT_PASSWORD)


def _make_user_doc(role: str = "medecin", password: str = _DEFAULT_PASSWORD) -> dict:
    oid = ObjectId()
    # Reuse the pre-computed hash when the caller uses the default password.
    pw_hash = _DEFAULT_PASSWORD_HASH if password == _DEFAULT_PASSWORD else hash_password(password)
    return {
        "_id": oid,
        "email": "doc@example.com",
        "password_hash": pw_hash,
        "role": role,
        "full_name": "Dr. Test",
        "locale": "fr",
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
    }


def _valid_token(user_id: str, role: str = "medecin") -> str:
    return create_access_token(user_id=user_id, role=role)


def _expired_token(user_id: str, role: str = "medecin") -> str:
    expire = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# 3. POST /login
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLoginEndpoint:
    async def test_valid_credentials_return_token(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        user_doc = _make_user_doc(password="password123")
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=user_doc)
        mock_collection.update_one = AsyncMock(return_value=None)
        mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="rt_id"))

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("backend.routers.auth.db") as mock_db_obj, \
             patch("backend.core.auth.db") as mock_core_db_obj, \
             patch("backend.services.audit_service.db") as mock_audit_db_obj:
            mock_db_obj.get_db.return_value = mock_db
            mock_core_db_obj.get_db.return_value = mock_db
            audit_collection = MagicMock()
            audit_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_id"))
            audit_mock_db = MagicMock()
            audit_mock_db.__getitem__ = MagicMock(return_value=audit_collection)
            mock_audit_db_obj.get_db.return_value = audit_mock_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/auth/login",
                    data={"username": "doc@example.com", "password": "password123"},
                )

        assert resp.status_code == 200
        body = resp.json()
        # Tokens are now in cookies, not in the response body
        assert "access_token" not in body
        assert "refresh_token" not in body
        assert body["token_type"] == "bearer"
        assert "expires_in" in body
        # Verify cookies are set
        assert "access_token" in resp.cookies
        assert "refresh_token" in resp.cookies
        assert "csrf_token" in resp.cookies

    async def test_invalid_password_returns_401(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        user_doc = _make_user_doc(password="correctpassword")
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=user_doc)

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("backend.routers.auth.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/auth/login",
                    data={"username": "doc@example.com", "password": "wrongpassword"},
                )

        assert resp.status_code == 401

    async def test_unknown_user_returns_401(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("backend.routers.auth.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/auth/login",
                    data={"username": "nobody@example.com", "password": "password123"},
                )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 4. POST /logout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLogoutEndpoint:
    async def test_valid_token_returns_200(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))

        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=user_doc)

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("backend.routers.auth.db") as mock_db_obj, \
             patch("backend.core.auth.db") as mock_core_db_obj, \
             patch("backend.services.audit_service.db") as mock_audit_db_obj:
            mock_db_obj.get_db.return_value = mock_db
            mock_core_db_obj.get_db.return_value = mock_db
            audit_collection = MagicMock()
            audit_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_id"))
            audit_mock_db = MagicMock()
            audit_mock_db.__getitem__ = MagicMock(return_value=audit_collection)
            mock_audit_db_obj.get_db.return_value = audit_mock_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/auth/logout",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 5. GET /me
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMeEndpoint:
    async def test_valid_token_returns_user_info(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))

        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=user_doc)

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("backend.routers.auth.db") as mock_db_obj, \
             patch("backend.core.auth.db") as mock_core_db_obj:
            mock_db_obj.get_db.return_value = mock_db
            mock_core_db_obj.get_db.return_value = mock_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "doc@example.com"
        assert body["role"] == "medecin"

    async def test_no_token_returns_401(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/auth/me")

        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer not.a.valid.token"},
            )

        assert resp.status_code == 401

    async def test_expired_token_returns_401(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        user_doc = _make_user_doc()
        token = _expired_token(str(user_doc["_id"]))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 6. require_role
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRequireRole:
    async def test_correct_role_passes(self):
        from backend.core.auth import require_role

        user_doc = {"_id": ObjectId(), "email": "admin@example.com", "role": "admin"}
        dep = require_role(["admin"])

        # Simulate calling the inner dependency with the user already resolved
        result = await dep(current_user=user_doc)
        assert result == user_doc

    async def test_wrong_role_raises_403(self):
        from backend.core.auth import require_role

        user_doc = {"_id": ObjectId(), "email": "doc@example.com", "role": "medecin"}
        dep = require_role(["admin"])

        with pytest.raises(HTTPException) as exc_info:
            await dep(current_user=user_doc)

        assert exc_info.value.status_code == 403

    async def test_multiple_allowed_roles(self):
        from backend.core.auth import require_role

        user_doc = {"_id": ObjectId(), "email": "pharm@example.com", "role": "pharmacien"}
        dep = require_role(["admin", "pharmacien"])

        result = await dep(current_user=user_doc)
        assert result == user_doc


# ---------------------------------------------------------------------------
# 7. Expired JWT — get_current_user raises 401
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestExpiredJWT:
    async def test_expired_token_raises_401_in_get_current_user(self):
        from backend.core.auth import get_current_user
        from unittest.mock import MagicMock

        user_id = str(ObjectId())
        token = _expired_token(user_id)

        mock_request = MagicMock()
        mock_request.cookies = {}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=mock_request, token=token)

        assert exc_info.value.status_code == 401

    async def test_tampered_token_raises_401(self):
        from backend.core.auth import get_current_user
        from unittest.mock import MagicMock

        token = _valid_token(str(ObjectId())) + "tampered"

        mock_request = MagicMock()
        mock_request.cookies = {}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=mock_request, token=token)

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# 8. POST /refresh
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRefreshEndpoint:
    def _make_token_doc(self, user_id: str, revoked: bool = False, expired: bool = False):
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        if expired:
            expires_at = now - timedelta(days=1)
        else:
            expires_at = now + timedelta(days=7)
        return {
            "token": "valid-refresh-token-uuid",
            "user_id": user_id,
            "expires_at": expires_at,
            "revoked": revoked,
        }

    async def test_valid_refresh_token_returns_new_tokens(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        user_doc = _make_user_doc()
        user_id = str(user_doc["_id"])
        token_doc = self._make_token_doc(user_id)

        mock_rt_collection = MagicMock()
        mock_rt_collection.find_one = AsyncMock(return_value=token_doc)
        mock_rt_collection.update_one = AsyncMock(return_value=None)
        mock_rt_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="new_rt"))

        mock_users_collection = MagicMock()
        mock_users_collection.find_one = AsyncMock(return_value=user_doc)

        def get_collection(name):
            if name == "refresh_tokens":
                return mock_rt_collection
            return mock_users_collection

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(side_effect=get_collection)

        with patch("backend.routers.auth.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                client.cookies.set("refresh_token", "valid-refresh-token-uuid")
                resp = await client.post(
                    "/api/v1/auth/refresh",
                )

        assert resp.status_code == 200
        body = resp.json()
        # Tokens are now in cookies, not in the response body
        assert "access_token" not in body
        assert "refresh_token" not in body
        assert body["token_type"] == "bearer"
        assert "expires_in" in body

    async def test_revoked_refresh_token_returns_401(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        user_doc = _make_user_doc()
        token_doc = self._make_token_doc(str(user_doc["_id"]), revoked=True)

        mock_rt_collection = MagicMock()
        mock_rt_collection.find_one = AsyncMock(return_value=token_doc)

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_rt_collection)

        with patch("backend.routers.auth.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                client.cookies.set("refresh_token", "revoked-token")
                resp = await client.post(
                    "/api/v1/auth/refresh",
                )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "refresh_token_invalid"

    async def test_expired_refresh_token_returns_401(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        user_doc = _make_user_doc()
        token_doc = self._make_token_doc(str(user_doc["_id"]), expired=True)

        mock_rt_collection = MagicMock()
        mock_rt_collection.find_one = AsyncMock(return_value=token_doc)

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_rt_collection)

        with patch("backend.routers.auth.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                client.cookies.set("refresh_token", "expired-token")
                resp = await client.post(
                    "/api/v1/auth/refresh",
                )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "refresh_token_invalid"

    async def test_unknown_refresh_token_returns_401(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        mock_rt_collection = MagicMock()
        mock_rt_collection.find_one = AsyncMock(return_value=None)

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_rt_collection)

        with patch("backend.routers.auth.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                client.cookies.set("refresh_token", "unknown-token")
                resp = await client.post(
                    "/api/v1/auth/refresh",
                )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "refresh_token_invalid"

    async def test_refresh_rotates_token(self):
        """After a successful refresh, the old token must be revoked (update_one called)."""
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        user_doc = _make_user_doc()
        user_id = str(user_doc["_id"])
        token_doc = self._make_token_doc(user_id)

        mock_rt_collection = MagicMock()
        mock_rt_collection.find_one = AsyncMock(return_value=token_doc)
        mock_rt_collection.update_one = AsyncMock(return_value=None)
        mock_rt_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="new_rt"))

        mock_users_collection = MagicMock()
        mock_users_collection.find_one = AsyncMock(return_value=user_doc)

        def get_collection(name):
            if name == "refresh_tokens":
                return mock_rt_collection
            return mock_users_collection

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(side_effect=get_collection)

        with patch("backend.routers.auth.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                client.cookies.set("refresh_token", "valid-refresh-token-uuid")
                await client.post(
                    "/api/v1/auth/refresh",
                )

        # Verify old token was revoked
        mock_rt_collection.update_one.assert_called_once()
        call_args = mock_rt_collection.update_one.call_args
        assert call_args[0][0] == {"token": "valid-refresh-token-uuid"}
        assert call_args[0][1] == {"$set": {"revoked": True}}


# ---------------------------------------------------------------------------
# 9. Property-based test — P7 : Rotation des refresh tokens
# Feature: diagno-pilot-improvements, Property 7: Rotation des refresh tokens — l'ancien token est invalidé après usage
# Validates: Requirements 4.3, 4.4
# ---------------------------------------------------------------------------

from hypothesis import given, settings as h_settings, HealthCheck  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

h_settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
h_settings.load_profile("ci")


def _make_refresh_token_doc(token_value: str, user_id: str, days_offset: int = 7) -> dict:
    """Build a valid (non-revoked, non-expired) refresh token document."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=days_offset)
    return {
        "token": token_value,
        "user_id": user_id,
        "expires_at": expires_at,
        "revoked": False,
    }


@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(
    token_suffix=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-",
        min_size=4,
        max_size=32,
    )
)
@pytest.mark.asyncio
async def test_p7_refresh_token_rotation_invalidates_old_token(token_suffix: str):
    """
    Property 7 — Rotation des refresh tokens.

    Pour tout refresh token valide T, après un appel réussi à POST /auth/refresh
    avec T, une seconde utilisation de T doit retourner HTTP 401 avec le message
    "refresh_token_invalid".

    # Feature: diagno-pilot-improvements, Property 7: Rotation des refresh tokens — l'ancien token est invalidé après usage
    # Validates: Requirements 4.3, 4.4
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    old_token_value = f"old-token-{token_suffix}"
    user_doc = _make_user_doc()
    user_id = str(user_doc["_id"])

    # Stateful in-memory store that simulates real MongoDB rotation behaviour
    token_store: dict[str, dict] = {
        old_token_value: _make_refresh_token_doc(old_token_value, user_id),
    }
    inserted_tokens: list[dict] = []

    async def fake_find_one(query: dict) -> dict | None:
        token_val = query.get("token")
        if token_val is None:
            return None
        doc = token_store.get(token_val)
        if doc is None:
            return None
        # Return a copy so mutations don't affect the store directly
        return dict(doc)

    async def fake_update_one(filter_: dict, update: dict) -> None:
        token_val = filter_.get("token")
        if token_val and token_val in token_store:
            set_fields = update.get("$set", {})
            token_store[token_val].update(set_fields)

    async def fake_insert_one(doc: dict):
        inserted_tokens.append(doc)
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

        # First use of old_token — must succeed (HTTP 200)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.cookies.set("refresh_token", old_token_value)
            first_resp = await client.post(
                "/api/v1/auth/refresh",
            )
        assert first_resp.status_code == 200, (
            f"Expected 200 on first refresh, got {first_resp.status_code}: {first_resp.text}"
        )

        # Second use of the same old_token — must be rejected (HTTP 401)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client2:
            client2.cookies.set("refresh_token", old_token_value)
            second_resp = await client2.post(
                "/api/v1/auth/refresh",
            )
        assert second_resp.status_code == 401, (
            f"Expected 401 on second use of old token, got {second_resp.status_code}: {second_resp.text}"
        )
        assert second_resp.json().get("detail") == "refresh_token_invalid", (
            f"Expected detail='refresh_token_invalid', got: {second_resp.json()}"
        )
