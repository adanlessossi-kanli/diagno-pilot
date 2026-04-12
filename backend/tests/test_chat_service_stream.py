"""Unit tests for ChatService.send_message_stream().

Validates: Requirements 5.1, 5.2, 5.3, 5.4

Updated for LLM-only ChatService (no RAG). Mocks now use StreamChunk
from LLMRouter instead of StreamEvent from LlamaIndexPipeline.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from backend.services.chat_service import ChatService
from backend.services.llm_router import StreamChunk


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


def _make_llm_mock(tokens: list[str], llm_used: str = "test-model", error: str | None = None):
    """Return a mock LLMRouter whose generate_stream yields StreamChunks.

    Args:
        tokens: List of token strings to yield.
        llm_used: Model name to include in chunks.
        error: If set, yield an error chunk after the tokens.
    """
    mock_llm = MagicMock()

    async def fake_generate_stream(prompt: str, context: list[dict]):
        for t in tokens:
            yield StreamChunk(token=t, llm_used=llm_used)
        if error:
            yield StreamChunk(error=error, llm_used=llm_used)

    mock_llm.generate_stream = fake_generate_stream
    return mock_llm


# ---------------------------------------------------------------------------
# Test: new session creation (Requirement 5.3)
# ---------------------------------------------------------------------------

def test_new_session_created_when_session_id_is_none():
    """When session_id is None, send_message_stream creates a new UUID session.

    Validates: Requirement 5.3
    """
    mock_db, mock_col = _make_mock_db()
    mock_llm = _make_llm_mock(["Hello"])
    service = ChatService(db=mock_db, llm_router=mock_llm)

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

    # Events forwarded correctly (token + done emitted by ChatService)
    assert [e.type for e in collected] == ["token", "done"]
    # Sources should always be empty (LLM-only, no RAG)
    done_event = [e for e in collected if e.type == "done"][0]
    assert done_event.sources == []


# ---------------------------------------------------------------------------
# Test: history loading and capping (Requirement 5.1)
# ---------------------------------------------------------------------------

def test_history_loaded_and_capped_at_20():
    """Session history is loaded and capped at 20 messages before querying LLM.

    Validates: Requirement 5.1
    """
    # Build a session with 30 messages
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}
        for i in range(30)
    ]
    mock_db, mock_col = _make_mock_db()
    mock_col.find_one = AsyncMock(return_value={"messages": messages})

    captured_args: dict = {}

    async def capturing_generate_stream(prompt: str, context: list[dict]):
        captured_args["prompt"] = prompt
        captured_args["context"] = context
        yield StreamChunk(token="ok", llm_used="m")

    mock_llm = MagicMock()
    mock_llm.generate_stream = capturing_generate_stream

    service = ChatService(db=mock_db, llm_router=mock_llm)

    async def run():
        collected = []
        async for ev in service.send_message_stream(
            session_id="existing-session", user_message="test",
        ):
            collected.append(ev)
        return collected

    _run(run())

    # Context passed to LLM should be capped at 20 messages
    context = captured_args.get("context", [])
    assert len(context) == 20
    # Should be the last 20 messages
    assert context[0]["content"] == "msg-10"
    assert context[-1]["content"] == "msg-29"


# ---------------------------------------------------------------------------
# Test: mid-stream error persists user turn only (Requirement 5.4)
# ---------------------------------------------------------------------------

def test_mid_stream_error_persists_user_turn_only():
    """On error chunk, only the user turn is persisted (no assistant turn).

    Validates: Requirement 5.4
    """
    mock_db, mock_col = _make_mock_db()
    mock_llm = _make_llm_mock(["partial"], error="LLM failed")
    service = ChatService(db=mock_db, llm_router=mock_llm)

    async def run():
        collected = []
        async for ev in service.send_message_stream(
            session_id="s1", user_message="hello", user_id="u1",
        ):
            collected.append(ev)
        return collected

    collected = _run(run())

    # Token + error events forwarded
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
    """On successful stream, both user and assistant turns are persisted.

    Validates: Requirement 5.2
    """
    mock_db, mock_col = _make_mock_db()
    mock_llm = _make_llm_mock(["The ", "answer"], llm_used="model-x")
    service = ChatService(db=mock_db, llm_router=mock_llm)

    async def run():
        collected = []
        async for ev in service.send_message_stream(
            session_id="s2", user_message="question", user_id="u2",
        ):
            collected.append(ev)
        return collected

    collected = _run(run())

    # Two token events + done event
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
    # Sources always empty in LLM-only mode (no RAG)
    assert assistant_turn["sources"] == []
