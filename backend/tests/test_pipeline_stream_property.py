# Feature: llm-response-streaming, Property 4: Stream Event Ordering
"""
Property 4: Stream Event Ordering

For any streaming query through LlamaIndexPipeline.query_stream(), the yielded
StreamEvent sequence SHALL consist of zero or more events with type="token"
followed by exactly one event with type="done" (or exactly one event with
type="error"), and no token events SHALL appear after the terminal event.

Validates: Requirements 3.2
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.document import DocumentSource, RAGResponse
from backend.services.llamaindex_pipeline import LlamaIndexPipeline, StreamEvent
from backend.services.llm_router import StreamChunk


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_token_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters=("\x00",),
    ),
)

_token_list_strategy = st.lists(_token_strategy, min_size=0, max_size=20)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_pipeline(router_chunks: list[StreamChunk]):
    """Create a LlamaIndexPipeline with mocked dependencies.

    The LLM router's generate_stream yields the provided StreamChunk list.
    IndexManager.retrieve returns empty list (simplest case).
    EmbeddingModel.encode returns a dummy vector.
    cache_service.get returns None (cache miss), cache_service.set is a no-op.
    """
    pipeline = LlamaIndexPipeline.__new__(LlamaIndexPipeline)

    # Mock IndexManager
    index = MagicMock()
    index.retrieve = AsyncMock(return_value=[])
    pipeline._index = index

    # Mock EmbeddingModel
    embedder = MagicMock()
    embedder.encode = AsyncMock(return_value=[0.0] * 128)
    pipeline._embedder = embedder

    # Mock LLMRouter
    router = MagicMock()

    async def fake_generate_stream(prompt, context):
        for chunk in router_chunks:
            yield chunk

    router.generate_stream = fake_generate_stream
    router.last_used = "test-model"
    pipeline._llm = router

    return pipeline


# ---------------------------------------------------------------------------
# Property 4: Stream Event Ordering
# ---------------------------------------------------------------------------

@given(tokens=_token_list_strategy)
@h_settings(max_examples=100, deadline=None)
def test_stream_event_ordering(tokens: list[str]):
    """
    # Feature: llm-response-streaming, Property 4: Stream Event Ordering

    For any random token sequence, the yielded StreamEvent sequence from
    query_stream() consists of zero or more token events followed by exactly
    one terminal event (done or error), with no token events after the
    terminal event.

    **Validates: Requirements 3.2**
    """
    # Build StreamChunks from the generated tokens
    chunks = [
        StreamChunk(token=t, llm_used="test-model")
        for t in tokens
    ]

    pipeline = _make_pipeline(chunks)

    async def run():
        events: list[StreamEvent] = []
        with patch("backend.services.llamaindex_pipeline.cache_service") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_cache.make_key = MagicMock(return_value="test-key")
            async for event in pipeline.query_stream("test question"):
                events.append(event)
        return events

    events = _run(run())

    # --- Verify ordering properties ---

    # 1. There must be at least one event (the terminal event)
    assert len(events) >= 1, "Expected at least one event (terminal)"

    # 2. Classify events
    terminal_types = {"done", "error"}
    token_events = [e for e in events if e.type == "token"]
    terminal_events = [e for e in events if e.type in terminal_types]

    # 3. Exactly one terminal event
    assert len(terminal_events) == 1, (
        f"Expected exactly 1 terminal event, got {len(terminal_events)}: "
        f"{[e.type for e in events]}"
    )

    # 4. The terminal event is the last event
    assert events[-1].type in terminal_types, (
        f"Last event should be terminal, got type={events[-1].type}"
    )

    # 5. No token events after the terminal event
    terminal_index = next(
        i for i, e in enumerate(events) if e.type in terminal_types
    )
    events_after_terminal = events[terminal_index + 1:]
    assert all(e.type not in ("token",) for e in events_after_terminal), (
        "Found token events after the terminal event"
    )

    # 6. All events before the terminal are token events
    events_before_terminal = events[:terminal_index]
    assert all(e.type == "token" for e in events_before_terminal), (
        f"Non-token event found before terminal: "
        f"{[e.type for e in events_before_terminal]}"
    )

    # 7. Number of token events matches input tokens
    assert len(token_events) == len(tokens), (
        f"Expected {len(tokens)} token events, got {len(token_events)}"
    )


# ---------------------------------------------------------------------------
# Strategies for Property 5
# ---------------------------------------------------------------------------

_model_name_strategy = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L", "N"), blacklist_characters=("\x00",)),
)

_document_source_strategy = st.builds(
    DocumentSource,
    document_id=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
    title=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
    source=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
    section=st.none() | st.text(min_size=1, max_size=10),
    excerpt=st.none() | st.text(min_size=1, max_size=30),
    page=st.none() | st.integers(min_value=0, max_value=500),
    highlight=st.none(),
    confidence_score=st.none() | st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)

_rag_response_strategy = st.builds(
    RAGResponse,
    answer=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), blacklist_characters=("\x00",)),
    ),
    sources=st.lists(_document_source_strategy, min_size=0, max_size=3),
    llm_used=_model_name_strategy,
    confidence=st.none(),
    confidence_score=st.none() | st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    degraded_warning=st.none(),
    grounding_warning=st.none(),
    fallback_used=st.booleans(),
)


# ---------------------------------------------------------------------------
# Property 5: Cache Hit Streaming
# ---------------------------------------------------------------------------

@given(response=_rag_response_strategy)
@h_settings(max_examples=100, deadline=None)
def test_cache_hit_streaming(response: RAGResponse):
    """
    # Feature: llm-response-streaming, Property 5: Cache Hit Streaming

    For any RAGResponse present in the cache for a given query,
    LlamaIndexPipeline.query_stream() SHALL yield exactly one StreamEvent
    with type="token" whose content equals the cached RAGResponse.answer,
    followed by exactly one StreamEvent with type="done" whose sources,
    llm_used, and fallback_used fields match the cached response — without
    invoking LLMRouter.generate_stream().

    **Validates: Requirements 3.3**
    """
    pipeline = LlamaIndexPipeline.__new__(LlamaIndexPipeline)

    # Mock IndexManager
    index = MagicMock()
    index.retrieve = AsyncMock(return_value=[])
    pipeline._index = index

    # Mock EmbeddingModel
    embedder = MagicMock()
    embedder.encode = AsyncMock(return_value=[0.0] * 128)
    pipeline._embedder = embedder

    # Mock LLMRouter — should NOT be called
    router = MagicMock()
    router.generate_stream = MagicMock(side_effect=AssertionError(
        "generate_stream should not be called on cache hit"
    ))
    router.last_used = "should-not-be-used"
    pipeline._llm = router

    async def run():
        events: list[StreamEvent] = []
        with patch("backend.services.llamaindex_pipeline.cache_service") as mock_cache:
            # Pre-populate cache: return the serialised RAGResponse
            mock_cache.get = AsyncMock(return_value=response.model_dump_json())
            mock_cache.set = AsyncMock()
            mock_cache.make_key = MagicMock(return_value="test-cache-key")
            async for event in pipeline.query_stream("test question"):
                events.append(event)
        return events

    events = _run(run())

    # --- Verify exactly 2 events: one token, one done ---
    assert len(events) == 2, (
        f"Expected exactly 2 events (1 token + 1 done), got {len(events)}: "
        f"{[(e.type, e.content) for e in events]}"
    )

    token_event = events[0]
    done_event = events[1]

    # --- Token event carries the cached answer ---
    assert token_event.type == "token", (
        f"First event should be 'token', got '{token_event.type}'"
    )
    assert token_event.content == response.answer, (
        f"Token content mismatch: expected {response.answer!r}, got {token_event.content!r}"
    )

    # --- Done event carries matching metadata ---
    assert done_event.type == "done", (
        f"Second event should be 'done', got '{done_event.type}'"
    )
    assert done_event.sources == response.sources, (
        f"Done sources mismatch: expected {response.sources}, got {done_event.sources}"
    )
    assert done_event.llm_used == response.llm_used, (
        f"Done llm_used mismatch: expected {response.llm_used!r}, got {done_event.llm_used!r}"
    )
    assert done_event.fallback_used == response.fallback_used, (
        f"Done fallback_used mismatch: expected {response.fallback_used}, got {done_event.fallback_used}"
    )

    # --- generate_stream was NOT called ---
    router.generate_stream.assert_not_called()
