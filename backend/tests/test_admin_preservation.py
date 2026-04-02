"""
Preservation property tests — UI/UX Navigation Overhaul bugfix spec.

These tests verify that EXISTING behaviors are NOT broken by future fixes.
They MUST PASS on the UNFIXED (current) code.

**Validates: Requirements 3.1, 3.7, 3.11**

Preserved behaviors confirmed by this file:
  - GET /api/v1/admin/stats still returns total_users, users_by_role, total_patients
  - GET /api/v1/admin/users still returns user list with same shape
  - PUT /api/v1/admin/users/{id} still works for non-self updates
  - Existing API contracts for /api/v1/admin/* are unchanged
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st

from backend.core.auth import get_current_user

# ---------------------------------------------------------------------------
# Hypothesis profile
# ---------------------------------------------------------------------------

h_settings.register_profile(
    "ci",
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
h_settings.load_profile("ci")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_admin_user() -> dict:
    oid = ObjectId()
    return {
        "_id": oid,
        "email": "admin@test.com",
        "role": "admin",
        "full_name": "Admin User",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }


def _make_other_user() -> dict:
    oid = ObjectId()
    return {
        "_id": oid,
        "email": "other@test.com",
        "role": "medecin",
        "full_name": "Other User",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }


def _make_mock_db(admin_user: dict, other_user: dict | None = None) -> MagicMock:
    """Build a minimal mock database."""
    users = [admin_user]
    if other_user:
        users.append(other_user)

    mock_users_col = MagicMock()
    mock_users_col.find_one = AsyncMock(
        side_effect=lambda query, *args, **kwargs: next(
            (
                u
                for u in users
                if str(u["_id"]) == str(query.get("_id", ""))
                or u["email"] == query.get("email", "")
            ),
            None,
        )
    )
    mock_users_col.count_documents = AsyncMock(return_value=len(users))
    mock_users_col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    cursor_mock = MagicMock()
    cursor_mock.to_list = AsyncMock(return_value=users)
    mock_users_col.find = MagicMock(return_value=cursor_mock)

    mock_patients_col = MagicMock()
    mock_patients_col.count_documents = AsyncMock(return_value=5)

    mock_audit_col = MagicMock()
    mock_audit_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_id"))

    mock_db = MagicMock()

    def get_col(name: str):
        if name == "users":
            return mock_users_col
        if name == "patients":
            return mock_patients_col
        if name == "audit_logs":
            return mock_audit_col
        return MagicMock()

    mock_db.__getitem__ = MagicMock(side_effect=get_col)
    return mock_db


# ---------------------------------------------------------------------------
# Preservation: GET /api/v1/admin/stats still returns existing fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_preserves_total_users():
    """
    **Validates: Requirements 3.7, 3.11**

    Preservation: GET /api/v1/admin/stats MUST still return 'total_users'.
    This field existed before the fix and must remain after the fix.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    mock_db = _make_mock_db(admin_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/admin/stats")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "total_users" in body, (
        f"Preservation failure: 'total_users' missing from stats response. "
        f"Actual keys: {list(body.keys())}"
    )
    assert isinstance(body["total_users"], int), (
        f"Preservation failure: 'total_users' must be an int, got {type(body['total_users'])}"
    )


@pytest.mark.asyncio
async def test_stats_preserves_users_by_role():
    """
    **Validates: Requirements 3.7, 3.11**

    Preservation: GET /api/v1/admin/stats MUST still return 'users_by_role'.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    mock_db = _make_mock_db(admin_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/admin/stats")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert "users_by_role" in body, (
        f"Preservation failure: 'users_by_role' missing from stats response. "
        f"Actual keys: {list(body.keys())}"
    )
    assert isinstance(body["users_by_role"], dict), (
        f"Preservation failure: 'users_by_role' must be a dict, got {type(body['users_by_role'])}"
    )


@pytest.mark.asyncio
async def test_stats_preserves_total_patients():
    """
    **Validates: Requirements 3.7, 3.11**

    Preservation: GET /api/v1/admin/stats MUST still return 'total_patients'.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    mock_db = _make_mock_db(admin_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/admin/stats")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert "total_patients" in body, (
        f"Preservation failure: 'total_patients' missing from stats response. "
        f"Actual keys: {list(body.keys())}"
    )
    assert isinstance(body["total_patients"], int), (
        f"Preservation failure: 'total_patients' must be an int, got {type(body['total_patients'])}"
    )


# ---------------------------------------------------------------------------
# Preservation: GET /api/v1/admin/users still returns user list with same shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_users_preserves_response_shape():
    """
    **Validates: Requirements 3.7, 3.11**

    Preservation: GET /api/v1/admin/users MUST still return a list of users
    with fields: id, email, role, full_name, is_active, created_at.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    other_user = _make_other_user()
    mock_db = _make_mock_db(admin_user, other_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/admin/users")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert isinstance(body, list), f"Preservation failure: expected list, got {type(body)}"
    assert len(body) >= 1, "Preservation failure: expected at least one user in response"

    # Verify each user has the expected shape
    required_fields = {"id", "email", "role", "full_name", "is_active", "created_at"}
    for user in body:
        missing = required_fields - set(user.keys())
        assert not missing, (
            f"Preservation failure: user response missing fields: {missing}. "
            f"Actual keys: {list(user.keys())}"
        )


@pytest.mark.asyncio
async def test_list_users_requires_admin_role():
    """
    **Validates: Requirements 3.7, 3.11**

    Preservation: GET /api/v1/admin/users MUST still require admin role (403 for non-admin).
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    non_admin_user = _make_other_user()  # role=medecin
    mock_db = _make_mock_db(non_admin_user)

    app.dependency_overrides[get_current_user] = lambda: non_admin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/admin/users")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403, (
        f"Preservation failure: non-admin should get 403, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Preservation: PUT /api/v1/admin/users/{id} still works for non-self updates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_other_user_still_works():
    """
    **Validates: Requirements 3.7, 3.11**

    Preservation: PUT /api/v1/admin/users/{id} MUST still return 200 for non-self updates.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    other_user = _make_other_user()
    other_oid = other_user["_id"]
    mock_db = _make_mock_db(admin_user, other_user)

    # Make find_one return the other user when queried by ObjectId
    mock_users_col = mock_db["users"]
    mock_users_col.find_one = AsyncMock(
        side_effect=lambda query, *args, **kwargs: (
            other_user if query.get("_id") == other_oid else None
        )
    )

    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/v1/admin/users/{other_oid}",
                    json={"role": "guest"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Preservation failure: PUT /api/v1/admin/users/{{other_id}} returned "
        f"{resp.status_code} (expected 200). Non-self update must still work."
    )


# ---------------------------------------------------------------------------
# Property test: stats always returns the three preserved fields
# ---------------------------------------------------------------------------

@given(st.text(min_size=0, max_size=0))  # single-run property (no meaningful input variation)
@h_settings(max_examples=3, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@pytest.mark.asyncio
async def test_stats_always_preserves_existing_fields(_unused: str):
    """
    **Validates: Requirements 3.7, 3.11**

    Property: GET /api/v1/admin/stats MUST always return all three pre-existing fields:
    total_users, users_by_role, total_patients.

    This is a preservation property — these fields must survive the fix.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    mock_db = _make_mock_db(admin_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/admin/stats")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    preserved_fields = {"total_users", "users_by_role", "total_patients"}
    missing = preserved_fields - set(body.keys())
    assert not missing, (
        f"Preservation failure: stats response missing pre-existing fields: {missing}. "
        f"Actual keys: {list(body.keys())}"
    )
