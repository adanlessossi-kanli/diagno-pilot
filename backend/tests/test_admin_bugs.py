"""
Bug condition exploration tests for UI/UX Navigation Overhaul bugfix spec.

These tests are written BEFORE any fix is applied. They assert the EXPECTED
(correct) behavior — and will FAIL on unfixed code, proving each bug exists.

**Validates: Requirements 1.10, 1.11, 1.12, 2.11, 2.12**

Bugs confirmed by this file:
  - Bug 1.11: GET /api/v1/admin/stats missing totalConsultations, totalDocuments, activeUsers
  - Bug 1.10: PATCH /api/v1/admin/users/{id}/role endpoint absent (404/405)
  - Bug 1.10: PATCH /api/v1/admin/users/{id}/status endpoint absent (404/405)
  - Bug 1.12: GET /api/v1/audit endpoint absent (404/405)
  - Bug 2.11/2.12: PUT /api/v1/admin/users/{self_id} has no self-guard (returns 200 instead of 403)

Counterexamples found (documented after running on unfixed code):
  - stats response keys: {'total_users', 'users_by_role', 'total_patients'} — missing totalConsultations, totalDocuments, activeUsers
  - PATCH /api/v1/admin/users/{id}/role → 404 or 405 (endpoint does not exist)
  - PATCH /api/v1/admin/users/{id}/status → 404 or 405 (endpoint does not exist)
  - GET /api/v1/audit → 404 (endpoint does not exist)
  - PUT /api/v1/admin/users/{self_id} with own id → 200 (self-guard missing)
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
    """Build a minimal mock database that returns users from the users collection."""
    users = [admin_user]
    if other_user:
        users.append(other_user)

    mock_users_col = MagicMock()
    mock_users_col.find_one = AsyncMock(
        side_effect=lambda query, *args, **kwargs: next(
            (u for u in users if str(u["_id"]) == str(query.get("_id", "")) or u["email"] == query.get("email", "")),
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
# Bug 1.11 — GET /api/v1/admin/stats missing new fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_has_total_consultations():
    """
    Bug 1.11: GET /api/v1/admin/stats MUST return totalConsultations.

    EXPECTED TO FAIL on unfixed code — stats only returns total_users,
    users_by_role, total_patients. Missing: totalConsultations.

    Counterexample: response body has no 'totalConsultations' key.
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
    # BUG 1.11: these keys are MISSING on unfixed code — test will FAIL
    assert "totalConsultations" in body, (
        f"Bug 1.11 confirmed: 'totalConsultations' missing from stats response. "
        f"Actual keys: {list(body.keys())}"
    )


@pytest.mark.asyncio
async def test_stats_has_total_documents():
    """
    Bug 1.11: GET /api/v1/admin/stats MUST return totalDocuments.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: response body has no 'totalDocuments' key.
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
    # BUG 1.11: 'totalDocuments' missing on unfixed code
    assert "totalDocuments" in body, (
        f"Bug 1.11 confirmed: 'totalDocuments' missing from stats response. "
        f"Actual keys: {list(body.keys())}"
    )


@pytest.mark.asyncio
async def test_stats_has_active_users():
    """
    Bug 1.11: GET /api/v1/admin/stats MUST return activeUsers.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: response body has no 'activeUsers' key.
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
    # BUG 1.11: 'activeUsers' missing on unfixed code
    assert "activeUsers" in body, (
        f"Bug 1.11 confirmed: 'activeUsers' missing from stats response. "
        f"Actual keys: {list(body.keys())}"
    )


# ---------------------------------------------------------------------------
# Bug 1.10 — PATCH /api/v1/admin/users/{id}/role endpoint absent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_user_role_endpoint_returns_200():
    """
    Bug 1.10: PATCH /api/v1/admin/users/{id}/role MUST return 200.

    EXPECTED TO FAIL on unfixed code — endpoint does not exist, returns 404/405.
    Counterexample: status_code is 404 or 405 (route not registered).
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    other_user = _make_other_user()
    mock_db = _make_mock_db(admin_user, other_user)

    # Make find_one return the other user when queried by ObjectId
    other_oid = other_user["_id"]
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
                resp = await client.patch(
                    f"/api/v1/admin/users/{other_oid}/role",
                    json={"role": "guest"},
                )
    finally:
        app.dependency_overrides.clear()

    # BUG 1.10: endpoint absent — will return 404 or 405 on unfixed code
    assert resp.status_code == 200, (
        f"Bug 1.10 confirmed: PATCH /api/v1/admin/users/{{id}}/role returned "
        f"{resp.status_code} (expected 200). Endpoint is absent."
    )


@pytest.mark.asyncio
async def test_patch_user_status_endpoint_returns_200():
    """
    Bug 1.10: PATCH /api/v1/admin/users/{id}/status MUST return 200.

    EXPECTED TO FAIL on unfixed code — endpoint does not exist, returns 404/405.
    Counterexample: status_code is 404 or 405 (route not registered).
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    other_user = _make_other_user()
    mock_db = _make_mock_db(admin_user, other_user)

    other_oid = other_user["_id"]
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
                resp = await client.patch(
                    f"/api/v1/admin/users/{other_oid}/status",
                    json={"is_active": False},
                )
    finally:
        app.dependency_overrides.clear()

    # BUG 1.10: endpoint absent — will return 404 or 405 on unfixed code
    assert resp.status_code == 200, (
        f"Bug 1.10 confirmed: PATCH /api/v1/admin/users/{{id}}/status returned "
        f"{resp.status_code} (expected 200). Endpoint is absent."
    )


# ---------------------------------------------------------------------------
# Bug 1.12 — GET /api/v1/audit endpoint absent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_endpoint_returns_200():
    """
    Bug 1.12: GET /api/v1/audit MUST return 200.

    EXPECTED TO FAIL on unfixed code — endpoint does not exist, returns 404.
    Counterexample: status_code is 404 (route not registered).
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    mock_db = _make_mock_db(admin_user)

    # Mock audit_logs collection with empty list
    mock_audit_col = MagicMock()
    audit_cursor = MagicMock()
    audit_cursor.to_list = AsyncMock(return_value=[])
    audit_cursor.skip = MagicMock(return_value=audit_cursor)
    audit_cursor.limit = MagicMock(return_value=audit_cursor)
    audit_cursor.sort = MagicMock(return_value=audit_cursor)
    mock_audit_col.find = MagicMock(return_value=audit_cursor)
    mock_audit_col.count_documents = AsyncMock(return_value=0)
    mock_audit_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_id"))

    def get_col(name: str):
        if name == "audit_logs":
            return mock_audit_col
        return mock_db[name]

    mock_db.__getitem__ = MagicMock(side_effect=get_col)

    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/audit")
    finally:
        app.dependency_overrides.clear()

    # BUG 1.12: endpoint absent — will return 404 on unfixed code
    assert resp.status_code == 200, (
        f"Bug 1.12 confirmed: GET /api/v1/audit returned "
        f"{resp.status_code} (expected 200). Endpoint is absent."
    )


# ---------------------------------------------------------------------------
# Bug 2.11/2.12 — PUT /api/v1/admin/users/{self_id} missing self-guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_self_user_returns_403():
    """
    Bug 2.11/2.12: PUT /api/v1/admin/users/{self_id} with own id MUST return 403.

    EXPECTED TO FAIL on unfixed code — self-guard is missing, returns 200.
    Counterexample: admin can demote themselves (status 200 instead of 403).
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    admin_oid = admin_user["_id"]
    mock_db = _make_mock_db(admin_user)

    mock_users_col = mock_db["users"]
    mock_users_col.find_one = AsyncMock(return_value=admin_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/v1/admin/users/{admin_oid}",
                    json={"role": "guest"},
                )
    finally:
        app.dependency_overrides.clear()

    # BUG 2.11/2.12: self-guard missing — returns 200 on unfixed code
    assert resp.status_code == 403, (
        f"Bug 2.11/2.12 confirmed: PUT /api/v1/admin/users/{{self_id}} returned "
        f"{resp.status_code} (expected 403). Self-guard is missing."
    )


# ---------------------------------------------------------------------------
# Property test — Bug 1.10: PATCH role endpoint absent for any valid role
# ---------------------------------------------------------------------------

@given(role=st.sampled_from(["admin", "medecin", "guest"]))
@h_settings(max_examples=3, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@pytest.mark.asyncio
async def test_patch_role_endpoint_exists_for_any_role(role: str):
    """
    **Validates: Requirements 1.10, 2.11**

    Property: For any valid role value, PATCH /api/v1/admin/users/{id}/role
    MUST return 200 (not 404/405).

    EXPECTED TO FAIL on unfixed code — endpoint does not exist.
    Counterexample: role='admin' → status 404 (endpoint absent).
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_admin_user()
    other_user = _make_other_user()
    mock_db = _make_mock_db(admin_user, other_user)

    other_oid = other_user["_id"]
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
                resp = await client.patch(
                    f"/api/v1/admin/users/{other_oid}/role",
                    json={"role": role},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Bug 1.10 confirmed for role={role!r}: "
        f"PATCH /api/v1/admin/users/{{id}}/role returned {resp.status_code}. "
        f"Endpoint is absent."
    )
