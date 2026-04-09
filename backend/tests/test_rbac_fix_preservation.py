"""
Preservation property tests — RBAC Fix bugfix spec (backend)

These tests verify that EXISTING correct behaviors are NOT broken by the fix.
They MUST PASS on the UNFIXED (current) code.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9**

Preserved behaviors confirmed by this file:
  - POST /api/v1/documents/upload with role='admin' returns 201
  - DELETE /api/v1/documents/{id} with role='admin' returns 204
  - POST /api/v1/chat/message with role='medecin' returns 200
  - GET /api/v1/patients with role='infirmière' returns 200
  - GET /api/v1/admin/users with role='admin' returns 200
  - GET /api/v1/admin/users with role='medecin' returns 403

Property 6: Preservation — for all roles NOT in bug condition, behavior is identical before/after fix.
"""
from __future__ import annotations

import io
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

def _make_user(role: str) -> dict:
    oid = ObjectId()
    return {
        "_id": oid,
        "email": f"{role.replace('è', 'e').replace('ê', 'e')}@test.com",
        "role": role,
        "full_name": f"Test {role.capitalize()}",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }


def _make_mock_db() -> MagicMock:
    """Build a minimal mock database."""
    mock_db = MagicMock()

    mock_users = MagicMock()
    mock_users.find_one = AsyncMock(return_value=None)
    mock_users.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    mock_users.count_documents = AsyncMock(return_value=0)
    cursor_mock = MagicMock()
    cursor_mock.to_list = AsyncMock(return_value=[])
    mock_users.find = MagicMock(return_value=cursor_mock)

    mock_audit = MagicMock()
    mock_audit.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

    mock_patients = MagicMock()
    mock_patients.count_documents = AsyncMock(return_value=0)
    patients_cursor = MagicMock()
    patients_cursor.to_list = AsyncMock(return_value=[])
    patients_cursor.skip = MagicMock(return_value=patients_cursor)
    patients_cursor.limit = MagicMock(return_value=patients_cursor)
    mock_patients.find = MagicMock(return_value=patients_cursor)

    def get_col(name: str):
        if name == "users":
            return mock_users
        if name == "audit_logs":
            return mock_audit
        if name == "patients":
            return mock_patients
        return MagicMock()

    mock_db.__getitem__ = MagicMock(side_effect=get_col)
    return mock_db


def _make_mock_document_service() -> MagicMock:
    """Build a mock DocumentService that returns a fake document."""
    from backend.models.document import MedicalDocument
    fake_doc = MedicalDocument(
        id=str(ObjectId()),
        title="Test Document",
        source="CHU_LOME",
        filename="test.pdf",
        chunk_count=1,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    mock_svc = MagicMock()
    mock_svc.ingest = AsyncMock(return_value=fake_doc)
    mock_svc.list_documents = AsyncMock(return_value=[])
    mock_svc.delete_document = AsyncMock(return_value=True)
    return mock_svc


def _make_mock_chat_service() -> MagicMock:
    """Build a mock ChatService that returns a fake streaming response."""
    mock_svc = MagicMock()

    async def _fake_stream(*args, **kwargs):
        from backend.services.llamaindex_pipeline import StreamEvent
        yield StreamEvent(type="token", content="Test answer")
        yield StreamEvent(type="done", answer="Test answer", sources=[], llm_used="test-model")

    mock_svc.send_message_stream = MagicMock(side_effect=_fake_stream)
    return mock_svc


# ---------------------------------------------------------------------------
# Preservation 3.6: POST /api/v1/documents/upload with role='admin' returns 201
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_admin_returns_201():
    """
    **Validates: Requirements 3.6**

    Preservation: POST /api/v1/documents/upload with role='admin' MUST continue to return 201.
    This is existing correct behavior — must not be broken by the fix.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.routers.documents import _get_document_service

    admin_user = _make_user("admin")
    mock_db = _make_mock_db()
    mock_svc = _make_mock_document_service()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[_get_document_service] = lambda: mock_svc

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db), \
             patch("backend.core.cache.cache_service.flush_pattern", new_callable=AsyncMock, return_value=0):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/documents/upload",
                    files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
                    data={"title": "Test Document", "source": "CHU_LOME"},
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201, (
        f"Preservation failure: POST /api/v1/documents/upload with role='admin' returned "
        f"{resp.status_code} (expected 201). Admin upload must continue to work."
    )


# ---------------------------------------------------------------------------
# Preservation 3.6: DELETE /api/v1/documents/{id} with role='admin' returns 204
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_document_admin_returns_204():
    """
    **Validates: Requirements 3.6**

    Preservation: DELETE /api/v1/documents/{id} with role='admin' MUST continue to return 204.
    This is existing correct behavior — must not be broken by the fix.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.routers.documents import _get_document_service

    admin_user = _make_user("admin")
    mock_db = _make_mock_db()
    mock_svc = _make_mock_document_service()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[_get_document_service] = lambda: mock_svc

    fake_doc_id = str(ObjectId())

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.delete(
                    f"/api/v1/documents/{fake_doc_id}",
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204, (
        f"Preservation failure: DELETE /api/v1/documents/{{id}} with role='admin' returned "
        f"{resp.status_code} (expected 204). Admin delete must continue to work."
    )


# ---------------------------------------------------------------------------
# Preservation 3.7: POST /api/v1/chat/message with role='medecin' returns 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_medecin_returns_200():
    """
    **Validates: Requirements 3.7**

    Preservation: POST /api/v1/chat/message with role='medecin' MUST continue to return 200.
    This is existing correct behavior — must not be broken by the fix.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.routers.chat import get_chat_service

    medecin_user = _make_user("medecin")
    mock_svc = _make_mock_chat_service()

    app.dependency_overrides[get_current_user] = lambda: medecin_user
    app.dependency_overrides[get_chat_service] = lambda: mock_svc

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/chat/message",
                json={"message": "Bonjour, j'ai besoin d'aide.", "session_id": None},
                headers={"Authorization": "Bearer fake"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Preservation failure: POST /api/v1/chat/message with role='medecin' returned "
        f"{resp.status_code} (expected 200). Medecin chat access must continue to work."
    )


# ---------------------------------------------------------------------------
# Preservation 3.7: GET /api/v1/patients with role='infirmière' returns 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patients_infirmiere_returns_200():
    """
    **Validates: Requirements 3.7**

    Preservation: GET /api/v1/patients with role='infirmière' MUST continue to return 200.
    This is existing correct behavior — must not be broken by the fix.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    infirmiere_user = _make_user("infirmière")
    mock_db = _make_mock_db()

    app.dependency_overrides[get_current_user] = lambda: infirmiere_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.patient_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/patients",
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Preservation failure: GET /api/v1/patients with role='infirmière' returned "
        f"{resp.status_code} (expected 200). Infirmière patient access must continue to work."
    )


# ---------------------------------------------------------------------------
# Preservation 3.8: GET /api/v1/admin/users with role='admin' returns 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_users_admin_returns_200():
    """
    **Validates: Requirements 3.8**

    Preservation: GET /api/v1/admin/users with role='admin' MUST continue to return 200.
    This is existing correct behavior — must not be broken by the fix.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    admin_user = _make_user("admin")
    mock_db = _make_mock_db()

    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/admin/users",
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Preservation failure: GET /api/v1/admin/users with role='admin' returned "
        f"{resp.status_code} (expected 200). Admin user management must continue to work."
    )


# ---------------------------------------------------------------------------
# Preservation 3.4: GET /api/v1/admin/users with role='medecin' returns 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_users_medecin_returns_403():
    """
    **Validates: Requirements 3.4**

    Preservation: GET /api/v1/admin/users with role='medecin' MUST continue to return 403.
    Non-admin roles must not access admin endpoints — this must be preserved.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    medecin_user = _make_user("medecin")
    mock_db = _make_mock_db()

    app.dependency_overrides[get_current_user] = lambda: medecin_user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/admin/users",
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403, (
        f"Preservation failure: GET /api/v1/admin/users with role='medecin' returned "
        f"{resp.status_code} (expected 403). Non-admin must continue to be blocked from admin endpoints."
    )


# ---------------------------------------------------------------------------
# Preservation 3.6: DELETE /api/v1/documents/{id} with non-admin returns 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_document_medecin_returns_403():
    """
    **Validates: Requirements 3.6**

    Preservation: DELETE /api/v1/documents/{id} with role='medecin' MUST continue to return 403.
    Document deletion is admin-only — this must be preserved after the fix.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.routers.documents import _get_document_service

    medecin_user = _make_user("medecin")
    mock_db = _make_mock_db()
    mock_svc = _make_mock_document_service()

    app.dependency_overrides[get_current_user] = lambda: medecin_user
    app.dependency_overrides[_get_document_service] = lambda: mock_svc

    fake_doc_id = str(ObjectId())

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.delete(
                    f"/api/v1/documents/{fake_doc_id}",
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403, (
        f"Preservation failure: DELETE /api/v1/documents/{{id}} with role='medecin' returned "
        f"{resp.status_code} (expected 403). Document deletion must remain admin-only."
    )


# ---------------------------------------------------------------------------
# Property: for all roles NOT in bug condition, behavior is identical before/after fix
# ---------------------------------------------------------------------------

@given(role=st.sampled_from(["admin", "medecin", "infirmière"]))
@h_settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@pytest.mark.asyncio
async def test_chat_non_buggy_roles_return_200(role: str):
    """
    **Validates: Requirements 3.5, 3.6, 3.7**

    Property 6: For all roles NOT in bug condition (admin, medecin, infirmière),
    POST /api/v1/chat/message MUST continue to return 200.

    These roles are already allowed in chat.py — behavior must be preserved.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.routers.chat import get_chat_service

    user = _make_user(role)
    mock_svc = _make_mock_chat_service()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_chat_service] = lambda: mock_svc

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/chat/message",
                json={"message": "Test message", "session_id": None},
                headers={"Authorization": "Bearer fake"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Preservation failure: POST /api/v1/chat/message with role={role!r} returned "
        f"{resp.status_code} (expected 200). Non-buggy role chat access must be preserved."
    )


@given(role=st.sampled_from(["admin", "medecin", "infirmière"]))
@h_settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@pytest.mark.asyncio
async def test_patients_non_buggy_roles_return_200(role: str):
    """
    **Validates: Requirements 3.6, 3.7**

    Property 6: For all roles NOT in bug condition (admin, medecin, infirmière),
    GET /api/v1/patients MUST continue to return 200.

    These roles are already allowed in patients.py — behavior must be preserved.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    user = _make_user(role)
    mock_db = _make_mock_db()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.patient_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/patients",
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Preservation failure: GET /api/v1/patients with role={role!r} returned "
        f"{resp.status_code} (expected 200). Non-buggy role patient access must be preserved."
    )


@given(role=st.sampled_from(["infirmière", "guest"]))
@h_settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@pytest.mark.asyncio
async def test_upload_unauthorized_roles_still_return_403(role: str):
    """
    **Validates: Requirements 3.6**

    Property 6: For roles NOT authorized to upload (infirmière, guest),
    POST /api/v1/documents/upload MUST continue to return 403 after the fix.

    This is a preservation property — the fix must not accidentally allow these roles.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.routers.documents import _get_document_service

    user = _make_user(role)
    mock_db = _make_mock_db()
    mock_svc = _make_mock_document_service()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[_get_document_service] = lambda: mock_svc

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db), \
             patch("backend.core.cache.cache_service.flush_pattern", new_callable=AsyncMock, return_value=0):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/documents/upload",
                    files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
                    data={"title": "Test", "source": "CHU_LOME"},
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403, (
        f"Preservation failure: POST /api/v1/documents/upload with role={role!r} returned "
        f"{resp.status_code} (expected 403). Unauthorized roles must remain blocked."
    )


@given(role=st.sampled_from(["medecin", "infirmière", "guest"]))
@h_settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@pytest.mark.asyncio
async def test_admin_users_non_admin_roles_return_403(role: str):
    """
    **Validates: Requirements 3.4, 3.8**

    Property 6: For all non-admin roles, GET /api/v1/admin/users MUST continue to return 403.
    Admin panel access must remain restricted to admin role only.
    MUST PASS on unfixed code.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    user = _make_user(role)
    mock_db = _make_mock_db()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db), \
             patch("backend.services.audit_service.db.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/admin/users",
                    headers={"Authorization": "Bearer fake"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403, (
        f"Preservation failure: GET /api/v1/admin/users with role={role!r} returned "
        f"{resp.status_code} (expected 403). Non-admin must remain blocked from admin endpoints."
    )
