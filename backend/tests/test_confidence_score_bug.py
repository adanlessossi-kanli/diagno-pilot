"""Bug condition exploration test — confidence_score not populated from chunk scores.

This property-based test encodes the EXPECTED behavior: every DocumentSource
constructed from a chunk with a valid ce_score or score SHALL have its
confidence_score populated (not None).

On UNFIXED code this test MUST FAIL, confirming the bug exists.
After the fix is applied, the test will pass.

Validates: Requirements 1.1, 2.1
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.document import DocumentSource
from backend.services.llamaindex_pipeline import LlamaIndexPipeline, StreamEvent
from backend.services.llm_router import LLMResult, StreamChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_pipeline(router_chunks: list[StreamChunk], chunks: list[dict] | None = None):
    """Create a LlamaIndexPipeline with mocked dependencies.

    Reuses the pattern from test_pipeline_stream.py.
    """
    pipeline = LlamaIndexPipeline.__new__(LlamaIndexPipeline)

    # Mock IndexManager
    index = MagicMock()
    index.retrieve = AsyncMock(return_value=chunks if chunks is not None else [])
    pipeline._index = index

    # Mock EmbeddingModel
    embedder = MagicMock()
    embedder.encode = AsyncMock(return_value=[0.0] * 128)
    pipeline._embedder = embedder

    # Mock LLMRouter — streaming
    router = MagicMock()

    async def fake_generate_stream(prompt, context):
        for chunk in router_chunks:
            yield chunk

    router.generate_stream = fake_generate_stream
    router.last_used = "test-model"

    # Mock LLMRouter — non-streaming (for query())
    router.generate = AsyncMock(
        return_value=LLMResult(answer="Test answer", fallback_used=False)
    )

    pipeline._llm = router
    return pipeline


# ---------------------------------------------------------------------------
# Strategies — generate chunk dicts with valid scores above threshold
# ---------------------------------------------------------------------------

# Scores that pass SOURCE_RELEVANCE_THRESHOLD (0.3)
above_threshold_score = st.floats(min_value=0.3, max_value=1.0, allow_nan=False)

# Chunk with ce_score (preferred path)
chunk_with_ce_score = st.fixed_dictionaries({
    "document_id": st.just("doc-1"),
    "metadata": st.just({"title": "Test Doc", "source": "TestOrg", "section": "S1"}),
    "content": st.just("Test content for retrieval."),
    "ce_score": above_threshold_score,
})

# Chunk with only score (fallback path — no ce_score)
chunk_with_score_only = st.fixed_dictionaries({
    "document_id": st.just("doc-2"),
    "metadata": st.just({"title": "Fallback Doc", "source": "FallbackOrg", "section": "S2"}),
    "content": st.just("Fallback content for retrieval."),
    "score": above_threshold_score,
})

# Mixed: chunk may have ce_score, score, or both
chunk_with_any_score = st.one_of(chunk_with_ce_score, chunk_with_score_only)

# Non-empty list of chunks (1-3 chunks to keep tests fast)
chunk_list_strategy = st.lists(chunk_with_any_score, min_size=1, max_size=3)


# ---------------------------------------------------------------------------
# Property 1: Bug Condition — query() path
# ---------------------------------------------------------------------------

@given(chunks=chunk_list_strategy)
@h_settings(max_examples=50)
def test_query_confidence_score_populated(chunks: list[dict]):
    """**Validates: Requirements 1.1, 2.1**

    Property: For all chunk dicts where ce_score or score is present and
    >= SOURCE_RELEVANCE_THRESHOLD, the resulting DocumentSource.confidence_score
    SHALL equal float(chunk.get("ce_score", chunk.get("score", 0.0)))
    and SHALL NOT be None.

    Tests the query() (non-streaming) code path.
    """
    router_chunks = [StreamChunk(token="Answer", llm_used="test-model")]
    pipeline = _make_pipeline(router_chunks, chunks=chunks)

    async def run():
        with patch("backend.services.llamaindex_pipeline.cache_service") as mock_cache, \
             patch("backend.services.llamaindex_pipeline.settings") as mock_settings:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_cache.make_key = MagicMock(return_value="test-key")
            mock_settings.SOURCE_RELEVANCE_THRESHOLD = 0.3
            mock_settings.CACHE_TTL_RAG = 300
            return await pipeline.query("test question")

    response = _run(run())

    # The pipeline sorts chunks by score descending and takes top 5
    sorted_chunks = sorted(
        chunks,
        key=lambda c: float(c.get("ce_score", c.get("score", 0.0))),
        reverse=True,
    )[:5]

    # Every source must have confidence_score populated
    assert len(response.sources) > 0, "Expected at least one source"
    for i, source in enumerate(response.sources):
        assert source.confidence_score is not None, (
            f"Source {i} (doc={source.document_id}) has confidence_score=None "
            f"despite chunk having a valid score"
        )
        # Verify the score matches the expected value from the sorted chunk
        chunk = sorted_chunks[i]
        expected = float(chunk.get("ce_score", chunk.get("score", 0.0)))
        assert source.confidence_score == expected, (
            f"Source {i} confidence_score={source.confidence_score}, "
            f"expected={expected}"
        )


# ---------------------------------------------------------------------------
# Property 1: Bug Condition — query_stream() path
# ---------------------------------------------------------------------------

@given(chunks=chunk_list_strategy)
@h_settings(max_examples=50)
def test_query_stream_confidence_score_populated(chunks: list[dict]):
    """**Validates: Requirements 1.1, 2.1**

    Property: For all chunk dicts where ce_score or score is present and
    >= SOURCE_RELEVANCE_THRESHOLD, the resulting DocumentSource.confidence_score
    in the done event SHALL equal float(chunk.get("ce_score", chunk.get("score", 0.0)))
    and SHALL NOT be None.

    Tests the query_stream() (streaming) code path.
    """
    router_chunks = [StreamChunk(token="Answer", llm_used="test-model")]
    pipeline = _make_pipeline(router_chunks, chunks=chunks)

    async def run():
        events: list[StreamEvent] = []
        with patch("backend.services.llamaindex_pipeline.cache_service") as mock_cache, \
             patch("backend.services.llamaindex_pipeline.settings") as mock_settings:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_cache.make_key = MagicMock(return_value="test-key")
            mock_settings.SOURCE_RELEVANCE_THRESHOLD = 0.3
            mock_settings.CACHE_TTL_RAG = 300
            async for event in pipeline.query_stream("test question"):
                events.append(event)
        return events

    events = _run(run())

    done_events = [e for e in events if e.type == "done"]
    assert len(done_events) == 1, "Expected exactly one done event"
    done = done_events[0]

    assert done.sources is not None and len(done.sources) > 0, (
        "Expected at least one source in done event"
    )

    # The pipeline sorts chunks by score descending and takes top 5
    sorted_chunks = sorted(
        chunks,
        key=lambda c: float(c.get("ce_score", c.get("score", 0.0))),
        reverse=True,
    )[:5]

    for i, source in enumerate(done.sources):
        assert source.confidence_score is not None, (
            f"Source {i} (doc={source.document_id}) has confidence_score=None "
            f"despite chunk having a valid score"
        )
        chunk = sorted_chunks[i]
        expected = float(chunk.get("ce_score", chunk.get("score", 0.0)))
        assert source.confidence_score == expected, (
            f"Source {i} confidence_score={source.confidence_score}, "
            f"expected={expected}"
        )


# ---------------------------------------------------------------------------
# Property 1: Bug Condition — fallback (score only, no ce_score)
# ---------------------------------------------------------------------------

@given(chunks=st.lists(chunk_with_score_only, min_size=1, max_size=3))
@h_settings(max_examples=30)
def test_query_fallback_score_populated(chunks: list[dict]):
    """**Validates: Requirements 1.1, 2.1**

    Property: When chunks have only 'score' (no 'ce_score'), the
    DocumentSource.confidence_score SHALL fall back to the 'score' value.

    Tests the fallback path in query().
    """
    router_chunks = [StreamChunk(token="Answer", llm_used="test-model")]
    pipeline = _make_pipeline(router_chunks, chunks=chunks)

    async def run():
        with patch("backend.services.llamaindex_pipeline.cache_service") as mock_cache, \
             patch("backend.services.llamaindex_pipeline.settings") as mock_settings:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_cache.make_key = MagicMock(return_value="test-key")
            mock_settings.SOURCE_RELEVANCE_THRESHOLD = 0.3
            mock_settings.CACHE_TTL_RAG = 300
            return await pipeline.query("test question")

    response = _run(run())

    # The pipeline sorts chunks by score descending and takes top 5
    sorted_chunks = sorted(
        chunks,
        key=lambda c: float(c.get("ce_score", c.get("score", 0.0))),
        reverse=True,
    )[:5]

    assert len(response.sources) > 0, "Expected at least one source"
    for i, source in enumerate(response.sources):
        assert source.confidence_score is not None, (
            f"Source {i} has confidence_score=None despite chunk having score={sorted_chunks[i].get('score')}"
        )
        expected = float(sorted_chunks[i]["score"])
        assert source.confidence_score == expected, (
            f"Source {i} confidence_score={source.confidence_score}, expected={expected}"
        )
