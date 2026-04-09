"""Unit tests for ChatService.send_message_stream().

Validates: Requirements 5.1, 5.2, 5.3, 5.4
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock


from backend.models.document import DocumentSource
from backend.services.chat_service import ChatService
from backend.services.llamaindex_pipeline import StreamEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_mock_db():
    """Return a mock Motor database whose collection accepts upserts."""
    mock_db = MagicMock()
    mock_collection = AsyncMock()
    mock_collection.update_one = AsyncMock(return_value=None)
    mock_collection.find_one = AsyncMock(return_value=None)  # no prior session
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    return mock_db, mock_collection


def _make_rag_mock(events: list[StreamEvent]):
    """Return a mock LlamaIndexPipeline whose query_stream yields *events*."""
    mock_rag = MagicMock()

    async def fake_query_stream(**kwargs):
        for e in events:
            yield e

    mock_rag.query_stream = fake_query_stream
    return mock_rag


# ---------------------------------------------------------------------------
# Test: new session creation (Requirement 5.3)
# ---------------------------------------------------------------------------

def test_new_session_created_when_session_id_is_none():
    """When session_id is None, send_message_stream creates a new UUID session.

    Validates: Requirement 5.3
    """
    source = DocumentSource(
        document_id="doc1", title="T", source="SRC", section=None,
        excerpt=None, page=None,
    )
    events = [
        StreamEvent(type="token", content="Hello"),
        StreamEvent(
            type="done", answer="Hello", sources=[source],
            llm_used="test-model", fallback_used=False,
        ),
    ]
    mock_db, mock_col = _make_mock_db()
    mock_rag = _make_rag_mock(events)
    service = ChatService(db=mock_db, rag_service=mock_rag)

    async def run():
        collected = []
        async for ev in service.send_message_stream(
            session_id=None, user_message="hi", user_id="u1",
        ):
            collected.append(ev)
        return collected

    collected = _run(run())

    # A session was persisted (upsert called)
    assert mock_col.update_one.await_count == 1
    persist_call = mock_col.update_one.await_args
    filter_arg = persist_call[0][0]  # first positional arg
    # session_id in the filter should be a non-empty UUID string
    sid = filter_arg["session_id"]
    assert isinstance(sid, str) and len(sid) > 0

    # Events forwarded correctly
    assert [e.type for e in collected] == ["token", "done"]


# ---------------------------------------------------------------------------
# Test: history loading and capping (Requirement 5.1)
# ---------------------------------------------------------------------------

def test_history_loaded_and_capped_at_20():
    """Session history is loaded and capped at 20 messages before querying RAG.

    Validates: Requirement 5.1
    """
    # Build a session with 30 messages
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}
        for i in range(30)
    ]
    mock_db, mock_col = _make_mock_db()
    mock_col.find_one = AsyncMock(return_value={"messages": messages})

    captured_kwargs: dict = {}

    async def capturing_query_stream(**kwargs):
        captured_kwargs.update(kwargs)
        yield StreamEvent(type="token", content="ok")
        yield StreamEvent(type="done", answer="ok", sources=[], llm_used="m")

    mock_rag = MagicMock()
    mock_rag.query_stream = capturing_query_stream

    service = ChatService(db=mock_db, rag_service=mock_rag)

    async def run():
        collected = []
        async for ev in service.send_message_stream(
            session_id="existing-session", user_message="test",
        ):
            collected.append(ev)
        return collected

    _run(run())

    # History passed to RAG should be capped at 20
    history = captured_kwargs.get("session_history", [])
    assert len(history) == 20
    # Should be the last 20 messages
    assert history[0]["content"] == "msg-10"
    assert history[-1]["content"] == "msg-29"


# ---------------------------------------------------------------------------
# Test: mid-stream error persists user turn only (Requirement 5.4)
# ---------------------------------------------------------------------------

def test_mid_stream_error_persists_user_turn_only():
    """On error event, only the user turn is persisted (no assistant turn).

    Validates: Requirement 5.4
    """
    events = [
        StreamEvent(type="token", content="partial"),
        StreamEvent(type="error", error="LLM failed", retryable=True),
    ]
    mock_db, mock_col = _make_mock_db()
    mock_rag = _make_rag_mock(events)
    service = ChatService(db=mock_db, rag_service=mock_rag)

    async def run():
        collected = []
        async for ev in service.send_message_stream(
            session_id="s1", user_message="hello", user_id="u1",
        ):
            collected.append(ev)
        return collected

    collected = _run(run())

    # Both events forwarded
    assert [e.type for e in collected] == ["token", "error"]

    # Exactly one DB write (user turn only)
    assert mock_col.update_one.await_count == 1
    update_arg = mock_col.update_one.await_args[0][1]  # second positional arg
    pushed = update_arg["$push"]
    # Should push a single message (user turn), not $each with two
    assert "messages" in pushed
    assert "$each" not in pushed.get("messages", {})
    assert pushed["messages"]["role"] == "user"
    assert pushed["messages"]["content"] == "hello"


# ---------------------------------------------------------------------------
# Test: successful stream persists both turns (Requirement 5.2)
# ---------------------------------------------------------------------------

def test_successful_stream_persists_both_turns():
    """On done event, both user and assistant turns are persisted.

    Validates: Requirement 5.2
    """
    source = DocumentSource(
        document_id="d1", title="Title", source="SRC",
        section=None, excerpt=None, page=None,
    )
    events = [
        StreamEvent(type="token", content="The "),
        StreamEvent(type="token", content="answer"),
        StreamEvent(
            type="done", answer="The answer", sources=[source],
            llm_used="model-x", fallback_used=False,
        ),
    ]
    mock_db, mock_col = _make_mock_db()
    mock_rag = _make_rag_mock(events)
    service = ChatService(db=mock_db, rag_service=mock_rag)

    async def run():
        collected = []
        async for ev in service.send_message_stream(
            session_id="s2", user_message="question", user_id="u2",
        ):
            collected.append(ev)
        return collected

    collected = _run(run())

    # All three events forwarded
    assert [e.type for e in collected] == ["token", "token", "done"]

    # Exactly one DB write with both turns
    assert mock_col.update_one.await_count == 1
    update_arg = mock_col.update_one.await_args[0][1]
    pushed = update_arg["$push"]["messages"]["$each"]
    assert len(pushed) == 2

    user_turn = pushed[0]
    assert user_turn["role"] == "user"
    assert user_turn["content"] == "question"

    assistant_turn = pushed[1]
    assert assistant_turn["role"] == "assistant"
    assert assistant_turn["content"] == "The answer"
    assert len(assistant_turn["sources"]) == 1
