# Feature: assistant-qa-and-documents-redesign, Property 3: Q&A Chat Persists Empty Sources Array
"""
Property test for Q&A Chat empty sources persistence.

**Validates: Requirements 1.4**

Property 3: Q&A Chat Persists Empty Sources Array
For any Q&A chat assistant turn, the persisted MongoDB session document SHALL
contain a `sources` field set to an empty array (`[]`), since the Q&A chat
no longer uses RAG or generates sources.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.chat_service import ChatService
from backend.services.llm_router import StreamChunk


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

message_strategy = st.text(min_size=1, max_size=200).filter(str.strip)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db():
    """Return a mock Motor database whose collection accepts upserts."""
    mock_db = MagicMock()
    mock_collection = AsyncMock()
    mock_collection.update_one = AsyncMock(return_value=None)
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    return mock_db, mock_collection


def _make_simple_llm_router(answer_text: str):
    """Return a mock LLMRouter that yields StreamChunk tokens."""
    mock_router = MagicMock()

    async def fake_generate_stream(prompt: str, context: list[dict]):
        for word in answer_text.split():
            yield StreamChunk(token=word + " ", llm_used="mock-llm")

    mock_router.generate_stream = fake_generate_stream
    return mock_router


# ---------------------------------------------------------------------------
# Property 3: Q&A Chat Persists Empty Sources Array
# ---------------------------------------------------------------------------

@given(message=message_strategy)
@h_settings(max_examples=100)
def test_qa_chat_persists_empty_sources_array(message: str):
    """
    **Validates: Requirements 1.4**

    For any user message, after send_message_stream() completes successfully:
    1. The done event should have `sources` as an empty list `[]`
    2. The MongoDB update_one call should persist the assistant turn with `sources: []`
    """
    mock_db, mock_collection = _make_mock_db()
    mock_router = _make_simple_llm_router("This is a medical answer.")
    service = ChatService(db=mock_db, llm_router=mock_router)

    async def _collect():
        events = []
        async for event in service.send_message_stream(
            session_id=None,
            user_message=message,
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())

    # --- Verify done event has sources == [] ---
    done_events = [e for e in events if e.type == "done"]
    assert len(done_events) == 1, (
        f"Expected exactly 1 done event, got {len(done_events)}"
    )
    done_event = done_events[0]
    assert done_event.sources == [], (
        f"Expected done event sources to be [], got {done_event.sources!r}"
    )

    # --- Verify MongoDB persistence includes sources: [] ---
    assert mock_collection.update_one.await_count == 1, (
        f"Expected exactly 1 update_one call, got {mock_collection.update_one.await_count}"
    )
    call_args = mock_collection.update_one.await_args[0]
    update_doc = call_args[1]  # second positional arg is the update document

    # The successful path pushes both user and assistant turns via $each
    pushed_messages = update_doc["$push"]["messages"]["$each"]
    assert len(pushed_messages) == 2, (
        f"Expected 2 pushed messages (user + assistant), got {len(pushed_messages)}"
    )

    assistant_turn = pushed_messages[1]
    assert assistant_turn["role"] == "assistant", (
        f"Expected second pushed message to be assistant, got {assistant_turn['role']!r}"
    )
    assert assistant_turn["sources"] == [], (
        f"Expected assistant turn sources to be [], got {assistant_turn['sources']!r}"
    )

    # Also verify user turn has sources: []
    user_turn = pushed_messages[0]
    assert user_turn["role"] == "user"
    assert user_turn["sources"] == [], (
        f"Expected user turn sources to be [], got {user_turn['sources']!r}"
    )
