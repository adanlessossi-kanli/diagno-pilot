"""
Bug condition exploration tests — RBAC Fix bugfix spec (backend)

These tests assert the EXPECTED (correct) behavior and will FAIL on unfixed
code, proving each bug exists. DO NOT fix the code when these fail.

**Validates: Requirements 1.3, 1.8, 2.3, 2.10**

Bugs confirmed by this file:
  - Bug 4: POST /api/v1/documents/upload with role='medecin' returns 403 (should be 201)
  - Bug 5: POST /api/v1/chat/message with role='infirmière' returns 403 (may already pass)
  - Property: admin and medecin get 201 on upload; infirmière and guest get 403

Expected counterexamples (on unfixed code):
  - medecin upload: require_role(["admin"]) raises HTTP 403 for medecin
  - infirmière chat: may already pass (chat.py already has infirmière in allowed roles)
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
        "email": f"{role}@test.com",
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
    mock_users.find.return_value.to_list = AsyncMock(return_value=[])

    mock_audit = MagicMock()
    mock_audit.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

    def get_col(name: str):
        if name == "users":
            return mock_users
        if name == "audit_logs":
            return mock_audit
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
# Bug 4 — POST /api/v1/documents/upload with role='medecin' returns 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_medecin_returns_201():
    """
    Bug 4: POST /api/v1/documents/upload with role='medecin' MUST return 201.

    EXPECTED TO FAIL on unfixed code — require_role(["admin"]) blocks medecin,
    returning HTTP 403.

    Counterexample: medecin upload → status_code=403 (should be 201).
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.routers.documents import _get_document_service

    medecin_user = _make_user("medecin")
    mock_db = _make_mock_db()
    mock_svc = _make_mock_document_service()

    app.dependency_overrides[get_current_user] = lambda: medecin_user
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

    # BUG 4: returns 403 on unfixed code (require_role(["admin"]) blocks medecin)
    assert resp.status_code == 201, (
        f"Bug 4 confirmed: POST /api/v1/documents/upload with role='medecin' returned "
        f"{resp.status_code} (expected 201). "
        f"Root cause: require_role([\"admin\"]) does not include 'medecin'."
    )


# ---------------------------------------------------------------------------
# Bug 5 — POST /api/v1/chat/message with role='infirmière' returns 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_infirmiere_not_403():
    """
    Bug 5: POST /api/v1/chat/message with role='infirmière' MUST NOT return 403.

    NOTE: This test may already PASS if chat.py already includes 'infirmière'
    in the allowed roles. Document the finding either way.

    Expected behavior: infirmière receives a valid response (non-403).
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.routers.chat import get_chat_service

    infirmiere_user = _make_user("infirmière")
    mock_svc = _make_mock_chat_service()

    app.dependency_overrides[get_current_user] = lambda: infirmiere_user
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

    # Bug 5: if chat.py already has infirmière, this passes (finding: bug already fixed)
    # If not, this fails with 403 (bug confirmed)
    assert resp.status_code != 403, (
        f"Bug 5 confirmed: POST /api/v1/chat/message with role='infirmière' returned 403. "
        f"Root cause: require_role does not include 'infirmière' in chat endpoint. "
        f"Response: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Property: upload returns 201 for admin/medecin, 403 for infirmière/guest
# ---------------------------------------------------------------------------

@given(role=st.sampled_from(["admin", "medecin"]))
@h_settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@pytest.mark.asyncio
async def test_upload_authorized_roles_return_201(role: str):
    """
    **Validates: Requirements 2.3**

    Property: For all authorized roles ['admin', 'medecin'],
    POST /api/v1/documents/upload MUST return 201.

    EXPECTED TO FAIL on unfixed code for role='medecin' (returns 403).
    Counterexample: role='medecin' → status_code=403 (should be 201).
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

    assert resp.status_code == 201, (
        f"Bug 4 confirmed for role={role!r}: upload returned {resp.status_code} "
        f"(expected 201). require_role([\"admin\"]) does not include '{role}'."
    )


@given(role=st.sampled_from(["infirmière", "guest"]))
@h_settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@pytest.mark.asyncio
async def test_upload_unauthorized_roles_return_403(role: str):
    """
    **Validates: Requirements 2.3**

    Property: For all unauthorized roles ['infirmière', 'guest'],
    POST /api/v1/documents/upload MUST return 403.

    This test MUST PASS on both unfixed and fixed code (preservation).
    Counterexample: if any unauthorized role gets 201, the fix is too permissive.
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
        f"Unexpected: upload returned {resp.status_code} for role={role!r} "
        f"(expected 403). Unauthorized role should be blocked."
    )
