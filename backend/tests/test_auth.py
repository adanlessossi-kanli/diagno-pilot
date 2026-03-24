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
from jose import jwt

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

def _make_user_doc(role: str = "medecin", password: str = "password123") -> dict:
    oid = ObjectId()
    return {
        "_id": oid,
        "email": "doc@example.com",
        "password_hash": hash_password(password),
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
        assert "access_token" in body
        assert body["token_type"] == "bearer"

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

        user_id = str(ObjectId())
        token = _expired_token(user_id)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token)

        assert exc_info.value.status_code == 401

    async def test_tampered_token_raises_401(self):
        from backend.core.auth import get_current_user

        token = _valid_token(str(ObjectId())) + "tampered"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token)

        assert exc_info.value.status_code == 401
