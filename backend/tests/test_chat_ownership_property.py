"""
Property test — Session ownership enforcement (Property 2).

Feature: chat-diagnosis-improvements, Property 2: Session ownership enforcement

For any (session_owner_id, requester_id, requester_role) triple, access to a
chat session SHALL be granted if and only if requester_id == session_owner_id
OR requester_role == "admin". In all other cases, the system SHALL return
HTTP 404.

**Validates: Requirements 2.1, 2.2, 2.4, 7.3, 7.4, 7.5, 13.1, 13.2, 13.3**
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings as h_settings, assume
from hypothesis import strategies as st

from backend.services.chat_service import ChatService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_user_id = st.uuids().map(str)
_role = st.sampled_from(["admin", "medecin", "infirmière", "guest"])
_session_id = st.uuids().map(str)


# ---------------------------------------------------------------------------
# Helpers — replicate the router ownership filter logic
# ---------------------------------------------------------------------------

def _compute_user_id_filter(requester_id: str, requester_role: str) -> str | None:
    """Replicate the router's ownership filter: admin bypasses, others filter."""
    return None if requester_role == "admin" else requester_id


# ---------------------------------------------------------------------------
# Property 2a: Owner can always access their own session
# ---------------------------------------------------------------------------

@given(owner_id=_user_id, role=_role, session_id=_session_id)
@h_settings(max_examples=100)
def test_owner_can_access_own_session(owner_id: str, role: str, session_id: str) -> None:
    """The session owner can always access their session regardless of role."""
    session_doc = {
        "session_id": session_id,
        "user_id": owner_id,
        "messages": [{"role": "user", "content": "hello"}],
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }

    mock_db = MagicMock()
    mock_collection = AsyncMock()

    def _find_one_side_effect(query, projection=None):
        """Return the doc only if the query matches owner_id or has no user_id filter."""
        if "user_id" in query:
            if query["user_id"] != owner_id:
                return AsyncMock(return_value=None)()
        return AsyncMock(return_value=session_doc)()

    mock_collection.find_one = MagicMock(side_effect=_find_one_side_effect)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    service = ChatService(db=mock_db, llm_router=AsyncMock())

    # Owner requests their own session
    user_id_filter = _compute_user_id_filter(owner_id, role)
    result = asyncio.run(service.get_history(session_id, user_id=user_id_filter))

    assert result is not None, "Owner should always be able to access their own session"
    assert result["session_id"] == session_id


# ---------------------------------------------------------------------------
# Property 2b: Non-admin non-owner gets None (404)
# ---------------------------------------------------------------------------

@given(
    owner_id=_user_id,
    requester_id=_user_id,
    requester_role=_role,
    session_id=_session_id,
)
@h_settings(max_examples=100)
def test_non_owner_non_admin_denied(
    owner_id: str, requester_id: str, requester_role: str, session_id: str
) -> None:
    """A non-admin user who is not the owner gets None (maps to 404)."""
    assume(requester_id != owner_id)
    assume(requester_role != "admin")

    session_doc = {
        "session_id": session_id,
        "user_id": owner_id,
        "messages": [],
    }

    mock_db = MagicMock()
    mock_collection = AsyncMock()

    def _find_one_side_effect(query, projection=None):
        if "user_id" in query and query["user_id"] != owner_id:
            return AsyncMock(return_value=None)()
        return AsyncMock(return_value=session_doc)()

    mock_collection.find_one = MagicMock(side_effect=_find_one_side_effect)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    service = ChatService(db=mock_db, llm_router=AsyncMock())

    user_id_filter = _compute_user_id_filter(requester_id, requester_role)
    result = asyncio.run(service.get_history(session_id, user_id=user_id_filter))

    assert result is None, (
        f"Non-owner non-admin should get None, but got {result!r}"
    )


# ---------------------------------------------------------------------------
# Property 2c: Admin can access any session
# ---------------------------------------------------------------------------

@given(owner_id=_user_id, admin_id=_user_id, session_id=_session_id)
@h_settings(max_examples=100)
def test_admin_can_access_any_session(
    owner_id: str, admin_id: str, session_id: str
) -> None:
    """An admin can access any session regardless of ownership."""
    assume(admin_id != owner_id)

    session_doc = {
        "session_id": session_id,
        "user_id": owner_id,
        "messages": [],
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }

    mock_db = MagicMock()
    mock_collection = AsyncMock()

    def _find_one_side_effect(query, projection=None):
        # Admin filter passes user_id=None, so no user_id in query
        if "user_id" not in query:
            return AsyncMock(return_value=session_doc)()
        if query["user_id"] == owner_id:
            return AsyncMock(return_value=session_doc)()
        return AsyncMock(return_value=None)()

    mock_collection.find_one = MagicMock(side_effect=_find_one_side_effect)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    service = ChatService(db=mock_db, llm_router=AsyncMock())

    # Admin: user_id_filter is None
    user_id_filter = _compute_user_id_filter(admin_id, "admin")
    assert user_id_filter is None

    result = asyncio.run(service.get_history(session_id, user_id=user_id_filter))

    assert result is not None, "Admin should be able to access any session"
    assert result["session_id"] == session_id


# ---------------------------------------------------------------------------
# Property 2d: Delete ownership enforcement
# ---------------------------------------------------------------------------

@given(
    owner_id=_user_id,
    requester_id=_user_id,
    requester_role=_role,
    session_id=_session_id,
)
@h_settings(max_examples=100)
def test_delete_ownership_enforcement(
    owner_id: str, requester_id: str, requester_role: str, session_id: str
) -> None:
    """Delete succeeds iff requester is owner or admin; fails otherwise."""
    mock_db = MagicMock()
    mock_collection = AsyncMock()

    class _DeleteResult:
        def __init__(self, count: int):
            self.deleted_count = count

    def _delete_one_side_effect(query):
        # Simulate: delete succeeds only if user_id matches or no user_id filter
        if "user_id" in query and query["user_id"] != owner_id:
            return AsyncMock(return_value=_DeleteResult(0))()
        return AsyncMock(return_value=_DeleteResult(1))()

    mock_collection.delete_one = MagicMock(side_effect=_delete_one_side_effect)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    service = ChatService(db=mock_db, llm_router=AsyncMock())

    user_id_filter = _compute_user_id_filter(requester_id, requester_role)
    deleted = asyncio.run(service.delete_session(session_id, user_id=user_id_filter))

    is_owner = requester_id == owner_id
    is_admin = requester_role == "admin"

    if is_owner or is_admin:
        assert deleted is True, "Owner or admin should be able to delete"
    else:
        assert deleted is False, "Non-owner non-admin should not be able to delete"
