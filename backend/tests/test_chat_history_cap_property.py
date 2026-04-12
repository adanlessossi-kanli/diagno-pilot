"""
Property test — History cap invariant (Property 1).

Feature: chat-diagnosis-improvements, Property 1: History cap invariant

For any chat session with N messages (where N >= 0), the context list
passed to LLMRouter.generate_stream() SHALL contain at most 20 messages,
and those 20 messages SHALL be the most recent ones from the session.

**Validates: Requirements 1.4**
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
    """Context passed to LLMRouter.generate_stream has at most 20 messages
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

    # --- Arrange: mock LLMRouter to capture context ----------------------
    captured_context: list[list[dict]] = []

    async def _capture_generate_stream(prompt: str, context: list[dict]):
        captured_context.append(context)
        yield StreamChunk(token="ok", llm_used="mock")

    mock_llm = MagicMock()
    mock_llm.generate_stream = _capture_generate_stream

    service = ChatService(db=mock_db, llm_router=mock_llm)

    # --- Act: send a message on an existing session ----------------------
    async def _run():
        async for _ in service.send_message_stream(
            session_id="existing-session",
            user_message="test",
        ):
            pass

    asyncio.run(_run())

    # --- Assert ----------------------------------------------------------
    assert len(captured_context) == 1, "generate_stream() should be called exactly once"
    context_passed = captured_context[0]

    # Property: at most 20 messages
    assert len(context_passed) <= 20, (
        f"Expected at most 20 messages in context, got {len(context_passed)}"
    )

    # Property: they are the most recent ones (mapped to role/content dicts)
    expected_messages = messages[-20:] if len(messages) > 20 else messages
    expected_context = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in expected_messages
    ]
    assert context_passed == expected_context, (
        "context must be the most recent messages from the session"
    )
