"""Property-based tests for the feedback router — diagno-pilot-improvements.

Feature: diagno-pilot-improvements
Property 15: Feedback de récupération stocké avec tous les champs requis
Validates: Requirements 4.7
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.core.auth import get_current_user


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_session_id_st = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"))
_doc_id_st = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"))
_chunk_id_st = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"))
_rating_st = st.sampled_from([1, -1])
_role_st = st.sampled_from(["admin", "medecin", "infirmière"])


def _make_user(role: str) -> dict:
    return {
        "_id": ObjectId(),
        "email": "user@test.com",
        "role": role,
        "full_name": "Test User",
        "is_active": True,
    }


# ---------------------------------------------------------------------------
# Feature: diagno-pilot-improvements, Property 15: Feedback stocké avec tous les champs requis
# Validates: Requirements 4.7
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    session_id=_session_id_st,
    document_id=_doc_id_st,
    chunk_id=_chunk_id_st,
    rating=_rating_st,
    role=_role_st,
)
async def test_property_15_feedback_stored_with_all_required_fields(
    session_id: str,
    document_id: str,
    chunk_id: str,
    rating: int,
    role: str,
):
    """Validates: Requirements 4.7
    For every valid submission to POST /api/v1/feedback/retrieval, the document
    inserted into retrieval_feedback must contain session_id, user_id, document_id,
    chunk_id, rating (1 or -1), and timestamp.
    """
    user = _make_user(role)
    inserted_id = ObjectId()

    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inserted_id))

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                cookies={"csrf_token": "test-csrf"},
            ) as client:
                resp = await client.post(
                    "/api/v1/feedback/retrieval",
                    json={
                        "session_id": session_id,
                        "document_id": document_id,
                        "chunk_id": chunk_id,
                        "rating": rating,
                    },
                    headers={"Authorization": "Bearer fake", "X-CSRF-Token": "test-csrf"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    # Verify insert_one was called exactly once
    mock_collection.insert_one.assert_called_once()

    # Verify the stored document contains all required fields
    stored_doc = mock_collection.insert_one.call_args.args[0]
    assert "session_id" in stored_doc, "Missing session_id in stored document"
    assert "user_id" in stored_doc, "Missing user_id in stored document"
    assert "document_id" in stored_doc, "Missing document_id in stored document"
    assert "chunk_id" in stored_doc, "Missing chunk_id in stored document"
    assert "rating" in stored_doc, "Missing rating in stored document"
    assert "timestamp" in stored_doc, "Missing timestamp in stored document"

    # Verify field values
    assert stored_doc["session_id"] == session_id
    assert stored_doc["document_id"] == document_id
    assert stored_doc["chunk_id"] == chunk_id
    assert stored_doc["rating"] == rating
    assert stored_doc["rating"] in (1, -1), f"rating must be 1 or -1, got {stored_doc['rating']}"
    assert stored_doc["user_id"] == str(user["_id"])


# ---------------------------------------------------------------------------
# Additional unit tests — invalid rating and unauthorized roles
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feedback_invalid_rating_returns_422():
    """Rating values other than 1 or -1 must be rejected with HTTP 422."""
    user = _make_user("medecin")
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"csrf_token": "test-csrf"},
        ) as client:
            resp = await client.post(
                "/api/v1/feedback/retrieval",
                json={
                    "session_id": "sess-1",
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "rating": 0,
                },
                headers={"Authorization": "Bearer fake", "X-CSRF-Token": "test-csrf"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422, f"Expected 422 for invalid rating, got {resp.status_code}"


@pytest.mark.asyncio
async def test_feedback_guest_role_returns_403():
    """Users with 'guest' role must be rejected with HTTP 403."""
    user = _make_user("guest")
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"csrf_token": "test-csrf"},
        ) as client:
            resp = await client.post(
                "/api/v1/feedback/retrieval",
                json={
                    "session_id": "sess-1",
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "rating": 1,
                },
                headers={"Authorization": "Bearer fake", "X-CSRF-Token": "test-csrf"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403, f"Expected 403 for guest role, got {resp.status_code}"
