"""
Tests unitaires pour le contrôle d'accès basé sur les rôles (RBAC) — Diagno-Pilot
"""
from __future__ import annotations

import pytest

from backend.core.auth import LEGACY_ROLE_MAP
from backend.models.common import UserRole


# ---------------------------------------------------------------------------
# Exemple 7.4 : type UserRole contient exactement les 4 valeurs attendues
# ---------------------------------------------------------------------------

def test_user_role_enum_has_exactly_four_values():
    """UserRole doit contenir exactement admin, medecin, infirmière, guest."""
    expected = {"admin", "medecin", "infirmière", "guest"}
    actual = {role.value for role in UserRole}
    assert actual == expected


# ---------------------------------------------------------------------------
# Exemple 6.4 : token avec rôle pharmacien → traité comme guest
# ---------------------------------------------------------------------------

def test_pharmacien_role_mapped_to_guest():
    """
    Exemple 6.4 : un token JWT contenant le rôle 'pharmacien' (rôle hérité)
    doit être traité avec les mêmes permissions que le rôle 'guest'.

    Validates: Requirements 6.4
    """
    # Le mapping doit exister dans LEGACY_ROLE_MAP
    assert "pharmacien" in LEGACY_ROLE_MAP
    assert LEGACY_ROLE_MAP["pharmacien"] == "guest"

    # Simuler le comportement de get_current_user sur un user_doc avec rôle pharmacien
    user_doc = {"_id": "some-id", "email": "pharma@example.com", "role": "pharmacien"}
    role = user_doc.get("role")
    effective_role = LEGACY_ROLE_MAP.get(role, role)

    assert effective_role == "guest", (
        f"Le rôle 'pharmacien' doit être mappé vers 'guest', obtenu: '{effective_role}'"
    )


def test_non_legacy_roles_not_remapped():
    """Les rôles valides actuels ne doivent pas être remappés par LEGACY_ROLE_MAP."""
    for role in ["admin", "medecin", "infirmière", "guest"]:
        effective = LEGACY_ROLE_MAP.get(role, role)
        assert effective == role, f"Le rôle '{role}' ne doit pas être remappé"


# ---------------------------------------------------------------------------
# Exemple 2.4 / 9.3 : POST /api/v1/qa sans JWT → HTTP 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_qa_endpoint_no_jwt_returns_200():
    """
    Exemple 2.4 : requête à /api/v1/qa sans JWT → HTTP 200.
    Exemple 9.3 : sans Authorization header → HTTP 200.

    Validates: Requirements 2.4, 9.1, 9.3
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/qa/",
            json={"question": "Quels sont les symptômes de la grippe ?"},
        )

    assert resp.status_code == 200, (
        f"Expected HTTP 200 without JWT, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "answer" in body


@pytest.mark.asyncio
async def test_qa_endpoint_no_authorization_header_returns_200():
    """
    Exemple 9.3 : /api/v1/qa sans Authorization header → HTTP 200.

    Validates: Requirements 9.3
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Explicitly ensure no Authorization header is sent
        resp = await client.post(
            "/api/v1/qa/",
            json={"question": "Qu'est-ce que la pénicilline ?"},
            headers={},
        )

    assert resp.status_code == 200, (
        f"Expected HTTP 200 without Authorization header, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Exemple 5.5 : attribution d'un rôle invalide lors de la création → HTTP 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_user_invalid_role_returns_422():
    """
    Exemple 5.5 : attribution d'un rôle invalide lors de la création → HTTP 422.
    Validates: Requirements 5.5
    """
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

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/admin/users",
                json={
                    "email": "new@test.com",
                    "password": "pass123",
                    "full_name": "New User",
                    "role": "pharmacien",
                },
                headers={"Authorization": "Bearer fake"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422, (
        f"Expected HTTP 422 for invalid role 'pharmacien', got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Exemple 1.3 : création d'utilisateur sans rôle → rôle guest par défaut
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_user_without_role_defaults_to_guest():
    """
    Exemple 1.3 : création d'un utilisateur sans rôle explicite → rôle 'guest' par défaut.
    Validates: Requirements 1.3
    """
    from unittest.mock import AsyncMock, MagicMock, patch
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

    inserted_id = ObjectId()

    # Mock the users collection
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)  # no existing user
    mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inserted_id))

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/admin/users",
                    json={
                        "email": "norolenewuser@test.com",
                        "password": "pass123",
                        "full_name": "No Role User",
                        # 'role' intentionally omitted — should default to 'guest'
                    },
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201, (
        f"Expected HTTP 201 for user creation without role, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["role"] == "guest", (
        f"Expected default role 'guest' when no role is specified, got '{body['role']}'"
    )
