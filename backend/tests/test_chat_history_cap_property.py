"""
Property test — History cap invariant (Property 1).

Feature: chat-diagnosis-improvements, Property 1: History cap invariant

For any chat session with N messages (where N >= 0), the session_history
passed to LlamaIndexPipeline.query() SHALL contain at most 20 messages,
and those 20 messages SHALL be the most recent ones from the session.

**Validates: Requirements 1.4**
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.document import RAGResponse
from backend.services.chat_service import ChatService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_message_dict = st.fixed_dictionaries(
    {
        "id": st.uuids().map(str),
        "role": st.sampled_from(["user", "assistant"]),
        "content": st.text(min_size=1, max_size=100).filter(str.strip),
        "sources": st.just([]),
        "timestamp": st.just("2025-01-01T00:00:00Z"),
    }
)

# Generate between 0 and 60 messages to exercise both under and over the cap
_messages_strategy = st.lists(_message_dict, min_size=0, max_size=60)


# ---------------------------------------------------------------------------
# Property 1: History cap invariant
# ---------------------------------------------------------------------------


@given(messages=_messages_strategy)
@h_settings(max_examples=100)
def test_history_cap_invariant(messages: list[dict]) -> None:
    """session_history passed to the pipeline has at most 20 messages
    and they are the most recent ones from the stored session."""

    # --- Arrange: mock DB to return the generated messages ---------------
    mock_db = MagicMock()
    mock_collection = AsyncMock()

    # _load_history does find_one with {"messages": 1, "_id": 0}
    mock_collection.find_one = AsyncMock(
        return_value={"messages": messages} if messages else None
    )
    # update_one for persisting turns
    mock_collection.update_one = AsyncMock(return_value=None)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    # --- Arrange: mock RAG pipeline to capture session_history -----------
    captured_history: list[list[dict]] = []

    async def _capture_query(**kwargs):
        captured_history.append(kwargs.get("session_history", []))
        return RAGResponse(
            answer="ok",
            sources=[],
            llm_used="mock",
        )

    mock_rag = AsyncMock()
    mock_rag.query = AsyncMock(side_effect=_capture_query)

    service = ChatService(db=mock_db, rag_service=mock_rag)

    # --- Act: send a message on an existing session ----------------------
    asyncio.run(
        service.send_message(
            session_id="existing-session",
            user_message="test",
        )
    )

    # --- Assert ----------------------------------------------------------
    assert len(captured_history) == 1, "query() should be called exactly once"
    history_passed = captured_history[0]

    # Property: at most 20 messages
    assert len(history_passed) <= 20, (
        f"Expected at most 20 messages in session_history, got {len(history_passed)}"
    )

    # Property: they are the most recent ones
    expected = messages[-20:] if len(messages) > 20 else messages
    assert history_passed == expected, (
        "session_history must be the most recent messages from the session"
    )
