"""
Tests de propriété pour le contrôle d'accès basé sur les rôles (RBAC) — Diagno-Pilot

Feature: role-based-access-control
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.models.common import UserRole

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ROLES = ["admin", "medecin", "infirmière", "guest"]
NON_ADMIN_ROLES = ["medecin", "infirmière", "guest"]
MEDICAL_ROLES = ["admin", "medecin", "infirmière"]

# ---------------------------------------------------------------------------
# Property 1 : Validation des rôles valides
# Feature: role-based-access-control, Property 1: Validation des rôles valides
# ---------------------------------------------------------------------------

@given(role=st.text())
@h_settings(max_examples=100)
def test_property_1_only_valid_roles_accepted(role: str):
    """
    # Feature: role-based-access-control, Property 1: Validation des rôles valides

    For any string value, it is accepted as a valid UserRole if and only if it
    belongs to {'admin', 'medecin', 'infirmière', 'guest'}.
    Any other string must be rejected.

    Validates: Requirements 1.1, 1.2
    """
    if role in VALID_ROLES:
        # Must be constructible from the enum
        user_role = UserRole(role)
        assert user_role.value == role
    else:
        with pytest.raises(ValueError):
            UserRole(role)

# ---------------------------------------------------------------------------
# Property 10 : Rétrocompatibilité des tokens JWT existants
# Feature: role-based-access-control, Property 10: Rétrocompatibilité des tokens JWT existants
# ---------------------------------------------------------------------------

from backend.core.auth import LEGACY_ROLE_MAP


@given(role=st.sampled_from(["medecin", "admin"]))
@h_settings(max_examples=100)
def test_property_10_legacy_tokens_accepted(role: str):
    """
    # Feature: role-based-access-control, Property 10: Rétrocompatibilité des tokens JWT existants

    For any token JWT containing the role 'medecin' or 'admin', the system must
    accept it and grant the same resources as before the extended RBAC introduction.
    These roles must not be remapped by LEGACY_ROLE_MAP.

    Validates: Requirements 6.3
    """
    # Les rôles medecin et admin ne doivent PAS être remappés
    effective_role = LEGACY_ROLE_MAP.get(role, role)
    assert effective_role == role, (
        f"Le rôle '{role}' ne doit pas être remappé par LEGACY_ROLE_MAP, "
        f"mais a été transformé en '{effective_role}'"
    )

    # Ces rôles doivent être des UserRole valides
    user_role = UserRole(role)
    assert user_role.value == role


# ---------------------------------------------------------------------------
# Property 3 : Admin autorisé sur tous les endpoints d'administration
# Feature: role-based-access-control, Property 3: Admin autorisé sur tous les endpoints d'administration
# ---------------------------------------------------------------------------

import asyncio

ADMIN_ENDPOINTS = [
    ("GET", "/api/v1/admin/users"),
    ("POST", "/api/v1/admin/users"),
    ("GET", "/api/v1/admin/stats"),
]


def _make_mock_db():
    """Return a MagicMock that mimics AsyncIOMotorDatabase for test purposes."""
    from unittest.mock import AsyncMock, MagicMock
    mock_db = MagicMock()
    # users collection
    mock_users = MagicMock()
    mock_users.find.return_value.to_list = AsyncMock(return_value=[])
    mock_users.find_one = AsyncMock(return_value=None)
    mock_users.insert_one = AsyncMock(return_value=MagicMock(inserted_id=__import__("bson").ObjectId()))
    mock_users.count_documents = AsyncMock(return_value=0)
    # patients collection
    mock_patients = MagicMock()
    mock_patients.count_documents = AsyncMock(return_value=0)
    # audit_logs collection
    mock_audit = MagicMock()
    mock_audit.insert_one = AsyncMock(return_value=MagicMock(inserted_id=__import__("bson").ObjectId()))

    def _getitem(name):
        if name == "users":
            return mock_users
        if name == "patients":
            return mock_patients
        if name == "audit_logs":
            return mock_audit
        return MagicMock()

    mock_db.__getitem__ = MagicMock(side_effect=_getitem)
    return mock_db


async def _test_property_3(role: str, endpoint: tuple[str, str]):
    from unittest.mock import patch
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.auth import get_current_user
    from bson import ObjectId

    admin_user = {
        "_id": ObjectId(),
        "email": "admin@test.com",
        "role": "admin",
        "full_name": "Admin",
        "is_active": True,
    }
    app.dependency_overrides[get_current_user] = lambda: admin_user

    method, path = endpoint
    mock_db = _make_mock_db()
    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                if method == "GET":
                    resp = await client.get(path, headers={"Authorization": "Bearer fake"})
                elif method == "POST":
                    resp = await client.post(
                        path,
                        json={
                            "email": f"u{ObjectId()}@test.com",
                            "password": "pass123",
                            "full_name": "Test",
                            "role": role,
                        },
                        headers={"Authorization": "Bearer fake"},
                    )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code not in (401, 403), (
        f"Admin should be authorized on {method} {path}, got {resp.status_code}"
    )


@given(
    role=st.just("admin"),
    endpoint=st.sampled_from(ADMIN_ENDPOINTS),
)
@h_settings(max_examples=100)
def test_property_3_admin_authorized_on_admin_endpoints(role: str, endpoint: tuple[str, str]):
    """
    # Feature: role-based-access-control, Property 3: Admin autorisé sur tous les endpoints d'administration
    For any request sent by a user with role 'admin' to any endpoint under /api/v1/admin/*,
    the response must not be 401 or 403.
    Validates: Requirements 2.1
    """
    asyncio.run(_test_property_3(role, endpoint))


# ---------------------------------------------------------------------------
# Property 4 : Non-admin rejeté sur les endpoints d'administration
# Feature: role-based-access-control, Property 4: Non-admin rejeté sur les endpoints d'administration
# ---------------------------------------------------------------------------


async def _test_property_4(role: str, endpoint: tuple[str, str]):
    from unittest.mock import patch
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.auth import get_current_user
    from bson import ObjectId

    non_admin_user = {
        "_id": ObjectId(),
        "email": f"{role}@test.com",
        "role": role,
        "full_name": "User",
        "is_active": True,
    }
    app.dependency_overrides[get_current_user] = lambda: non_admin_user

    method, path = endpoint
    mock_db = _make_mock_db()
    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                if method == "GET":
                    resp = await client.get(path, headers={"Authorization": "Bearer fake"})
                elif method == "POST":
                    resp = await client.post(
                        path,
                        json={"email": "x@test.com", "password": "pass", "full_name": "X"},
                        headers={"Authorization": "Bearer fake"},
                    )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403, (
        f"Non-admin role '{role}' should get 403 on {method} {path}, got {resp.status_code}"
    )


@given(
    role=st.sampled_from(NON_ADMIN_ROLES),
    endpoint=st.sampled_from(ADMIN_ENDPOINTS),
)
@h_settings(max_examples=100)
def test_property_4_non_admin_rejected_on_admin_endpoints(role: str, endpoint: tuple[str, str]):
    """
    # Feature: role-based-access-control, Property 4: Non-admin rejeté sur les endpoints d'administration
    For any user with a role other than 'admin', any request to /api/v1/admin/* must return HTTP 403.
    Validates: Requirements 2.2, 4.2, 5.3
    """
    asyncio.run(_test_property_4(role, endpoint))


# ---------------------------------------------------------------------------
# Property 5 : Rôles médicaux autorisés sur les ressources médicales
# Feature: role-based-access-control, Property 5: Rôles médicaux autorisés sur les ressources médicales
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Property 2 : Round-trip rôle via /auth/me
# Feature: role-based-access-control, Property 2: Round-trip rôle via /auth/me
# ---------------------------------------------------------------------------


async def _test_property_2(role: str):
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.auth import get_current_user
    from bson import ObjectId

    user = {
        "_id": ObjectId(),
        "email": f"{role}@test.com",
        "role": role,
        "full_name": "Test User",
        "locale": "fr",
        "is_active": True,
    }
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer fake"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Expected HTTP 200 from /auth/me for role '{role}', got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["role"] == role, (
        f"Round-trip failed: stored role '{role}' but /auth/me returned '{body.get('role')}'"
    )


@given(role=st.sampled_from(VALID_ROLES))
@h_settings(max_examples=100, deadline=None)
def test_property_2_role_round_trip_via_auth_me(role: str):
    """
    # Feature: role-based-access-control, Property 2: Round-trip rôle via /auth/me

    For any user created with a valid role, calling /api/v1/auth/me after
    authentication must return exactly the same role as the one stored in the
    database.

    Validates: Requirements 1.4, 7.1
    """
    asyncio.run(_test_property_2(role))


MEDICAL_ENDPOINTS = [
    ("GET", "/api/v1/patients"),
    ("GET", "/api/v1/chat/history/test-session"),
    ("GET", "/api/v1/diagnose/antibiotics"),
]


async def _test_property_5(role: str, endpoint: tuple[str, str]):
    from unittest.mock import AsyncMock, MagicMock, patch
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.auth import get_current_user
    from bson import ObjectId

    medical_user = {
        "_id": ObjectId(),
        "email": f"{role}@test.com",
        "role": role,
        "full_name": "User",
        "is_active": True,
    }
    app.dependency_overrides[get_current_user] = lambda: medical_user

    method, path = endpoint
    mock_db = _make_mock_db()

    # Add chat_sessions collection support (returns None → 404, not 401/403)
    mock_sessions = MagicMock()
    mock_sessions.find_one = AsyncMock(return_value=None)

    original_getitem = mock_db.__getitem__.side_effect

    def _extended_getitem(name):
        if name == "chat_sessions":
            return mock_sessions
        return original_getitem(name)

    mock_db.__getitem__ = MagicMock(side_effect=_extended_getitem)

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(path, headers={"Authorization": "Bearer fake"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code not in (401, 403), (
        f"Medical role '{role}' should be authorized on {method} {path}, got {resp.status_code}"
    )


@given(
    role=st.sampled_from(MEDICAL_ROLES),
    endpoint=st.sampled_from(MEDICAL_ENDPOINTS),
)
@h_settings(max_examples=100, deadline=None)
def test_property_5_medical_roles_authorized_on_medical_endpoints(role: str, endpoint: tuple[str, str]):
    """
    # Feature: role-based-access-control, Property 5: Rôles médicaux autorisés sur les ressources médicales

    For any user with role 'admin', 'medecin' or 'infirmière', any request to
    endpoints /api/v1/patients, /api/v1/diagnose or /api/v1/chat must be
    authorized (no 401 or 403).

    Validates: Requirements 2.3, 6.1
    """
    asyncio.run(_test_property_5(role, endpoint))


# ---------------------------------------------------------------------------
# Property 9 : Audit log contient les métadonnées requises
# Feature: role-based-access-control, Property 9: Audit log contient les métadonnées requises
# ---------------------------------------------------------------------------


async def _test_property_9_stats(role: str):
    """
    Vérifie que l'accès à GET /admin/stats crée une entrée d'audit
    contenant user_id, created_at (timestamp) et ip_address.
    """
    from unittest.mock import AsyncMock, MagicMock, patch, call
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.auth import get_current_user
    from bson import ObjectId

    admin_user = {
        "_id": ObjectId(),
        "email": "admin@test.com",
        "role": "admin",
        "full_name": "Admin",
        "is_active": True,
    }
    app.dependency_overrides[get_current_user] = lambda: admin_user

    captured_docs: list[dict] = []

    mock_db = _make_mock_db()

    # Override audit_logs insert_one to capture the document
    mock_audit = MagicMock()

    async def _capture_insert(doc):
        captured_docs.append(doc)
        return MagicMock(inserted_id=ObjectId())

    mock_audit.insert_one = _capture_insert

    original_getitem = mock_db.__getitem__.side_effect

    def _extended_getitem(name):
        if name == "audit_logs":
            return mock_audit
        return original_getitem(name)

    mock_db.__getitem__ = MagicMock(side_effect=_extended_getitem)

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/admin/stats",
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Expected 200 from GET /admin/stats, got {resp.status_code}: {resp.text}"
    )
    assert len(captured_docs) >= 1, (
        "Expected at least one audit log entry for GET /admin/stats, got none"
    )

    for doc in captured_docs:
        assert "user_id" in doc, f"Audit log entry missing 'user_id': {doc}"
        assert doc["user_id"], "Audit log 'user_id' must not be empty"
        assert "created_at" in doc, f"Audit log entry missing 'created_at' (timestamp): {doc}"
        assert doc["created_at"] is not None, "Audit log 'created_at' must not be None"
        assert "ip_address" in doc, f"Audit log entry missing 'ip_address': {doc}"


async def _test_property_9_update_user(role: str):
    """
    Vérifie que PUT /admin/users/{id} crée une entrée d'audit
    contenant user_id, created_at (timestamp) et ip_address.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.auth import get_current_user
    from bson import ObjectId
    from datetime import datetime, timezone

    admin_oid = ObjectId()
    target_oid = ObjectId()

    admin_user = {
        "_id": admin_oid,
        "email": "admin@test.com",
        "role": "admin",
        "full_name": "Admin",
        "is_active": True,
    }
    app.dependency_overrides[get_current_user] = lambda: admin_user

    captured_docs: list[dict] = []

    mock_db = _make_mock_db()

    # Mock users collection with a target user
    target_user_doc = {
        "_id": target_oid,
        "email": "target@test.com",
        "role": "guest",
        "full_name": "Target",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }

    mock_users = MagicMock()
    mock_users.find_one = AsyncMock(return_value=target_user_doc)
    mock_users.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_users.find.return_value.to_list = AsyncMock(return_value=[])
    mock_users.count_documents = AsyncMock(return_value=1)

    # Override audit_logs insert_one to capture the document
    mock_audit = MagicMock()

    async def _capture_insert(doc):
        captured_docs.append(doc)
        return MagicMock(inserted_id=ObjectId())

    mock_audit.insert_one = _capture_insert

    original_getitem = mock_db.__getitem__.side_effect

    def _extended_getitem(name):
        if name == "users":
            return mock_users
        if name == "audit_logs":
            return mock_audit
        return original_getitem(name)

    mock_db.__getitem__ = MagicMock(side_effect=_extended_getitem)

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/v1/admin/users/{str(target_oid)}",
                    json={"role": "medecin"},
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Expected 200 from PUT /admin/users/{{id}}, got {resp.status_code}: {resp.text}"
    )
    assert len(captured_docs) >= 1, (
        "Expected at least one audit log entry for PUT /admin/users/{id}, got none"
    )

    for doc in captured_docs:
        assert "user_id" in doc, f"Audit log entry missing 'user_id': {doc}"
        assert doc["user_id"], "Audit log 'user_id' must not be empty"
        assert "created_at" in doc, f"Audit log entry missing 'created_at' (timestamp): {doc}"
        assert doc["created_at"] is not None, "Audit log 'created_at' must not be None"
        assert "ip_address" in doc, f"Audit log entry missing 'ip_address': {doc}"


@given(role=st.just("admin"))
@h_settings(max_examples=100, deadline=None)
def test_property_9_audit_log_contains_required_metadata(role: str):
    """
    # Feature: role-based-access-control, Property 9: Audit log contient les métadonnées requises

    For any admin access to statistics or user role modification, the entry
    created in the audit log must contain the user identifier, a timestamp,
    and the IP address.

    Validates: Requirements 4.3, 5.4
    """
    asyncio.run(_test_property_9_stats(role))
    asyncio.run(_test_property_9_update_user(role))
