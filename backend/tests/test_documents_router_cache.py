"""
Unit tests for RAG cache flush on document upload — Diagno-Pilot

Validates: Requirements 5.5

After a successful document ingestion, the documents router must flush all
RAG cache entries by calling cache_service.flush_pattern with the key
produced by cache_service.make_key("rag", "*").
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from backend.core.auth import get_current_user
from backend.models.document import MedicalDocument
from backend.routers.documents import _get_document_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_admin_user() -> dict:
    return {
        "_id": ObjectId(),
        "email": "admin@test.com",
        "role": "admin",
        "full_name": "Admin User",
        "locale": "fr",
    }


def _make_medical_document() -> MedicalDocument:
    return MedicalDocument(
        id=str(ObjectId()),
        title="Test Document",
        source="CHU_LOME",
        s3_key="documents/test.txt",
        indexed_at=datetime.now(timezone.utc),
        chunk_count=3,
        created_at=datetime.now(timezone.utc),
    )


async def _noop_audit(*args, **kwargs) -> None:
    """No-op replacement for audit_service.log_action."""
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_document_flushes_rag_cache():
    """
    After successful ingestion, flush_pattern must be called with 'v1:rag:*'.
    Validates: Requirements 5.5
    """
    from backend.main import app

    admin_user = _make_admin_user()
    doc = _make_medical_document()

    mock_svc = MagicMock()
    mock_svc.ingest = AsyncMock(return_value=doc)

    mock_cache = MagicMock()
    mock_cache.flush_pattern = AsyncMock(return_value=3)
    mock_cache.make_key = MagicMock(return_value="v1:rag:*")

    async def mock_get_current_user():
        return admin_user

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[_get_document_service] = lambda: mock_svc

    try:
        with patch("backend.routers.documents.cache_service", mock_cache), \
             patch("backend.services.audit_service.audit_service.log_action", new=AsyncMock()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                from backend.routers.auth import create_access_token
                token = create_access_token(user_id=str(admin_user["_id"]), role="admin")

                response = await client.post(
                    "/api/v1/documents/upload",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": ("test.txt", b"Medical content", "text/plain")},
                    data={"title": "Test Document", "source": "CHU_LOME"},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(_get_document_service, None)

    assert response.status_code == 201
    mock_cache.make_key.assert_called_once_with("rag", "*")
    mock_cache.flush_pattern.assert_called_once_with("v1:rag:*")


@pytest.mark.asyncio
async def test_upload_document_flush_called_with_correct_key():
    """
    make_key("rag", "*") must be used as the argument to flush_pattern.
    Validates: Requirements 5.5
    """
    from backend.main import app

    admin_user = _make_admin_user()
    doc = _make_medical_document()

    mock_svc = MagicMock()
    mock_svc.ingest = AsyncMock(return_value=doc)

    mock_cache = MagicMock()
    mock_cache.flush_pattern = AsyncMock(return_value=0)
    mock_cache.make_key = MagicMock(return_value="v1:rag:*")

    async def mock_get_current_user():
        return admin_user

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[_get_document_service] = lambda: mock_svc

    try:
        with patch("backend.routers.documents.cache_service", mock_cache), \
             patch("backend.services.audit_service.audit_service.log_action", new=AsyncMock()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                from backend.routers.auth import create_access_token
                token = create_access_token(user_id=str(admin_user["_id"]), role="admin")

                await client.post(
                    "/api/v1/documents/upload",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": ("guide.txt", b"Content", "text/plain")},
                    data={"title": "Guide", "source": "OMS_AFRO"},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(_get_document_service, None)

    # The key passed to flush_pattern must be the result of make_key("rag", "*")
    flush_arg = mock_cache.flush_pattern.call_args[0][0]
    assert flush_arg == "v1:rag:*"


@pytest.mark.asyncio
async def test_upload_document_no_flush_on_ingest_failure():
    """
    If ingest raises an exception, flush_pattern must NOT be called.
    Validates: Requirements 5.5
    """
    from backend.main import app

    admin_user = _make_admin_user()

    mock_svc = MagicMock()
    mock_svc.ingest = AsyncMock(side_effect=Exception("S3 unavailable"))

    mock_cache = MagicMock()
    mock_cache.flush_pattern = AsyncMock(return_value=0)
    mock_cache.make_key = MagicMock(return_value="v1:rag:*")

    async def mock_get_current_user():
        return admin_user

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[_get_document_service] = lambda: mock_svc

    try:
        with patch("backend.routers.documents.cache_service", mock_cache), \
             patch("backend.services.audit_service.audit_service.log_action", new=AsyncMock()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                from backend.routers.auth import create_access_token
                token = create_access_token(user_id=str(admin_user["_id"]), role="admin")

                response = await client.post(
                    "/api/v1/documents/upload",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": ("doc.txt", b"Content", "text/plain")},
                    data={"title": "Doc", "source": "MSF"},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(_get_document_service, None)

    assert response.status_code == 500
    mock_cache.flush_pattern.assert_not_called()
