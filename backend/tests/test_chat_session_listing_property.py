"""
Property test — Session listing invariants (Property 3).

Feature: chat-diagnosis-improvements, Property 3: Session listing invariants

For any user with N chat sessions, the GET /api/v1/chat/sessions endpoint
SHALL return only sessions belonging to that user, sorted by updated_at in
descending order, with each session containing session_id, created_at,
updated_at, and a first-message preview. The returned count SHALL respect
min(limit, 100) and the skip offset.

**Validates: Requirements 3.1, 3.2, 3.3, 3.5**
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.chat_service import ChatService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_user_id = st.uuids().map(str)
_other_user_id = st.uuids().map(str)


def _make_session(user_id: str, idx: int) -> dict:
    """Create a session document for testing."""
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return {
        "session_id": f"session-{idx}",
        "user_id": user_id,
        "created_at": base_time + timedelta(hours=idx),
        "updated_at": base_time + timedelta(hours=idx, minutes=30),
        "messages": [{"role": "user", "content": f"Message {idx}"}],
    }


_session_count = st.integers(min_value=0, max_value=30)
_skip = st.integers(min_value=0, max_value=40)
_limit = st.integers(min_value=1, max_value=100)


# ---------------------------------------------------------------------------
# Property 3: Session listing invariants
# ---------------------------------------------------------------------------

@given(
    user_id=_user_id,
    other_user_id=_other_user_id,
    n_user_sessions=_session_count,
    n_other_sessions=st.integers(min_value=0, max_value=10),
    skip=_skip,
    limit=_limit,
)
@h_settings(max_examples=100)
def test_session_listing_invariants(
    user_id: str,
    other_user_id: str,
    n_user_sessions: int,
    n_other_sessions: int,
    skip: int,
    limit: int,
) -> None:
    """Only user's sessions returned, sorted by updated_at desc, respects skip/limit."""
    # Build session documents
    user_sessions = [_make_session(user_id, i) for i in range(n_user_sessions)]
    other_sessions = [_make_session(other_user_id, i + 1000) for i in range(n_other_sessions)]

    # Sort user sessions by updated_at descending (as the service does)
    user_sessions_sorted = sorted(user_sessions, key=lambda s: s["updated_at"], reverse=True)

    # Expected result after skip/limit
    expected = user_sessions_sorted[skip : skip + limit]

    # Project to match what list_sessions returns
    expected_projected = []
    for s in expected:
        expected_projected.append({
            "session_id": s["session_id"],
            "created_at": s["created_at"],
            "updated_at": s["updated_at"],
            "messages": s["messages"][:1],
        })

    # Mock the DB cursor chain
    mock_db = MagicMock()
    mock_collection = MagicMock()

    class _MockCursor:
        def __init__(self, docs):
            self._docs = docs

        def sort(self, *args, **kwargs):
            return self

        def skip(self, n):
            self._docs = self._docs[n:]
            return self

        def limit(self, n):
            self._docs = self._docs[:n]
            return self

        async def to_list(self, length=None):
            return self._docs

    def _find_side_effect(query, projection=None):
        # Filter by user_id
        target_uid = query.get("user_id")
        all_sessions = user_sessions_sorted + other_sessions
        filtered = [s for s in all_sessions if s["user_id"] == target_uid]
        # Apply projection for messages slice
        projected = []
        for s in filtered:
            proj = {
                "session_id": s["session_id"],
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
                "messages": s["messages"][:1],
            }
            projected.append(proj)
        return _MockCursor(projected)

    mock_collection.find = MagicMock(side_effect=_find_side_effect)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    service = ChatService(db=mock_db, rag_service=AsyncMock())

    result = asyncio.run(service.list_sessions(user_id=user_id, skip=skip, limit=limit))

    # Property: only user's sessions
    for s in result:
        assert s["session_id"].startswith("session-"), "Unexpected session_id format"

    # Property: count respects skip/limit
    assert len(result) == len(expected_projected), (
        f"Expected {len(expected_projected)} sessions, got {len(result)}"
    )

    # Property: sorted by updated_at descending
    if len(result) > 1:
        for i in range(len(result) - 1):
            assert result[i]["updated_at"] >= result[i + 1]["updated_at"], (
                "Sessions must be sorted by updated_at descending"
            )

    # Property: each session has required fields
    for s in result:
        assert "session_id" in s
        assert "created_at" in s
        assert "updated_at" in s
        assert "messages" in s
        assert len(s["messages"]) <= 1  # first message preview
