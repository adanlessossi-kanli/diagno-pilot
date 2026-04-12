"""Property-based tests for feedback endpoint authentication.

Feature: assistant-qa-and-documents-redesign
Property 12: Feedback Endpoint Authentication
Generate random roles. Verify all authenticated roles succeed,
unauthenticated returns 401.

**Validates: Requirements 13.4**
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
from backend.core.rate_limit import limiter


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

ALL_ROLES = ["admin", "medecin", "infirmière", "guest"]

_role_st = st.sampled_from(ALL_ROLES)
_question_st = st.text(min_size=1, max_size=200, alphabet=st.characters(
    whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
    whitelist_characters="?!.,'-"
))
_response_st = st.text(min_size=1, max_size=500, alphabet=st.characters(
    whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
    whitelist_characters="?!.,'-[]"
))


def _make_user(role: str) -> dict:
    return {
        "_id": ObjectId(),
        "email": "user@test.com",
        "role": role,
        "full_name": "Test User",
        "is_active": True,
    }


# ---------------------------------------------------------------------------
# Property 12: Feedback Endpoint Authentication — Authenticated roles succeed
# Validates: Requirements 13.4
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    role=_role_st,
    question=_question_st,
    response=_response_st,
)
async def test_property_12_authenticated_roles_succeed(
    role: str,
    question: str,
    response: str,
):
    """**Validates: Requirements 13.4**

    For any authenticated user with a role in {admin, medecin, infirmière, guest},
    POST /api/v1/chat/feedback SHALL return 200, since the endpoint uses
    get_current_user (not require_role) — all authenticated roles are accepted.
    """
    user = _make_user(role)

    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    app.dependency_overrides[get_current_user] = lambda: user
    original_enabled = limiter.enabled
    limiter.enabled = False

    try:
        with patch("backend.core.database.db.get_db", return_value=mock_db):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                cookies={"csrf_token": "test-csrf"},
            ) as client:
                resp = await client.post(
                    "/api/v1/chat/feedback",
                    json={"question": question, "response": response},
                    headers={
                        "Authorization": "Bearer fake",
                        "X-CSRF-Token": "test-csrf",
                    },
                )
    finally:
        limiter.enabled = original_enabled
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Authenticated role '{role}' should get 200, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Property 12: Feedback Endpoint Authentication — Unauthenticated returns 401
# Validates: Requirements 13.4
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_property_12_unauthenticated_returns_401():
    """**Validates: Requirements 13.4**

    An unauthenticated request (no token, no user) to POST /api/v1/chat/feedback
    SHALL return 401.
    """
    # Ensure no auth override is set
    app.dependency_overrides.pop(get_current_user, None)
    original_enabled = limiter.enabled
    limiter.enabled = False

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"csrf_token": "test-csrf"},
        ) as client:
            resp = await client.post(
                "/api/v1/chat/feedback",
                json={
                    "question": "What is malaria?",
                    "response": "[TOPIC_GUARD_REFUSAL]\nSorry...",
                },
                headers={"X-CSRF-Token": "test-csrf"},
            )
    finally:
        limiter.enabled = original_enabled
        app.dependency_overrides.clear()

    assert resp.status_code == 401, (
        f"Unauthenticated request should get 401, got {resp.status_code}: {resp.text}"
    )
