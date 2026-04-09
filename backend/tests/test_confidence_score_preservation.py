"""Preservation property tests — above-threshold sources and empty retrievals unchanged.

These tests verify EXISTING behavior on UNFIXED code to establish a baseline.
They confirm that:
- All above-threshold chunks produce the same number of sources (no sources dropped)
- Empty chunk lists produce empty sources
- The planned frontend filter preserves all sources with confidence_score >= 0.3
- The planned frontend filter retains sources with confidence_score = None (backward compat)

All tests MUST PASS on unfixed code.

Validates: Requirements 3.1, 3.2, 3.3, 3.5
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

    Reuses the pattern from test_pipeline_stream.py / test_confidence_score_bug.py.
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


def frontend_source_filter(sources: list[DocumentSource]) -> list[DocumentSource]:
    """Pure Python mirror of the planned JS frontend filter.

    JS: sources.filter(s => s.confidence_score == null || s.confidence_score >= 0.3)
    The == null loose equality matches both null and undefined.
    In Python, we check for None (equivalent to null/undefined).
    """
    return [s for s in sources if s.confidence_score is None or s.confidence_score >= 0.3]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Scores that pass SOURCE_RELEVANCE_THRESHOLD (0.3)
above_threshold_score = st.floats(min_value=0.3, max_value=1.0, allow_nan=False)

# Chunk with ce_score above threshold
above_threshold_chunk = st.fixed_dictionaries({
    "document_id": st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
    "metadata": st.fixed_dictionaries({
        "title": st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
        "source": st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
        "section": st.one_of(st.none(), st.text(min_size=1, max_size=15)),
    }),
    "content": st.text(min_size=1, max_size=100),
    "ce_score": above_threshold_score,
})

# Non-empty list of above-threshold chunks (1-5 to match top_k cap)
above_threshold_chunk_list = st.lists(above_threshold_chunk, min_size=1, max_size=5)

# DocumentSource with confidence_score >= 0.3
doc_source_above_threshold = st.builds(
    DocumentSource,
    document_id=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
    title=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
    source=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    section=st.one_of(st.none(), st.text(min_size=1, max_size=15)),
    excerpt=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    page=st.one_of(st.none(), st.integers(min_value=1, max_value=500)),
    confidence_score=above_threshold_score,
)

# DocumentSource with confidence_score = None (legacy cached data)
doc_source_none_score = st.builds(
    DocumentSource,
    document_id=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
    title=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
    source=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    section=st.one_of(st.none(), st.text(min_size=1, max_size=15)),
    excerpt=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    page=st.one_of(st.none(), st.integers(min_value=1, max_value=500)),
    confidence_score=st.none(),
)


# ---------------------------------------------------------------------------
# Backend Preservation: query() — all above-threshold → same count
# ---------------------------------------------------------------------------

@given(chunks=above_threshold_chunk_list)
@h_settings(max_examples=50)
def test_query_all_above_threshold_returns_all_sources(chunks: list[dict]):
    """**Validates: Requirements 3.1, 3.2**

    Property: When all chunks have ce_score >= 0.3 (above SOURCE_RELEVANCE_THRESHOLD),
    query() returns the same number of sources as chunks — no sources are dropped.
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

    assert len(response.sources) == len(chunks), (
        f"Expected {len(chunks)} sources but got {len(response.sources)}. "
        f"No above-threshold sources should be dropped."
    )


# ---------------------------------------------------------------------------
# Backend Preservation: query_stream() — all above-threshold → same count
# ---------------------------------------------------------------------------

@given(chunks=above_threshold_chunk_list)
@h_settings(max_examples=50)
def test_query_stream_all_above_threshold_returns_all_sources(chunks: list[dict]):
    """**Validates: Requirements 3.1, 3.2**

    Property: When all chunks have ce_score >= 0.3 (above SOURCE_RELEVANCE_THRESHOLD),
    query_stream() done event returns the same number of sources as chunks.
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

    assert done.sources is not None, "Done event sources should not be None"
    assert len(done.sources) == len(chunks), (
        f"Expected {len(chunks)} sources but got {len(done.sources)}. "
        f"No above-threshold sources should be dropped."
    )


# ---------------------------------------------------------------------------
# Backend Preservation: query() — empty chunks → empty sources
# ---------------------------------------------------------------------------

def test_query_empty_chunks_returns_empty_sources():
    """**Validates: Requirements 3.2**

    When no chunks are retrieved, query() returns an empty sources list.
    """
    router_chunks = [StreamChunk(token="Answer", llm_used="test-model")]
    pipeline = _make_pipeline(router_chunks, chunks=[])

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

    assert response.sources == [], (
        f"Expected empty sources list but got {len(response.sources)} sources"
    )


# ---------------------------------------------------------------------------
# Backend Preservation: query_stream() — empty chunks → empty sources
# ---------------------------------------------------------------------------

def test_query_stream_empty_chunks_returns_empty_sources():
    """**Validates: Requirements 3.2**

    When no chunks are retrieved, query_stream() done event returns empty sources.
    """
    router_chunks = [StreamChunk(token="Answer", llm_used="test-model")]
    pipeline = _make_pipeline(router_chunks, chunks=[])

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

    assert done.sources is not None, "Done event sources should not be None"
    assert len(done.sources) == 0, (
        f"Expected empty sources list but got {len(done.sources)} sources"
    )



# ---------------------------------------------------------------------------
# Frontend Filter Preservation: all above-threshold → identity
# ---------------------------------------------------------------------------

@given(sources=st.lists(doc_source_above_threshold, min_size=1, max_size=10))
@h_settings(max_examples=100)
def test_frontend_filter_all_above_threshold_identity(sources: list[DocumentSource]):
    """**Validates: Requirements 3.1, 3.5**

    Property: When all DocumentSource objects have confidence_score >= 0.3,
    the frontend filter returns the full list unchanged (identity).
    No sources are incorrectly removed.
    """
    filtered = frontend_source_filter(sources)

    assert len(filtered) == len(sources), (
        f"Expected {len(sources)} sources but filter returned {len(filtered)}. "
        f"All above-threshold sources should be preserved."
    )
    # Verify same objects in same order
    for i, (orig, filt) in enumerate(zip(sources, filtered)):
        assert orig is filt, (
            f"Source at index {i} was replaced or reordered by the filter"
        )


# ---------------------------------------------------------------------------
# Frontend Filter Preservation: None scores retained (backward compat)
# ---------------------------------------------------------------------------

@given(
    above=st.lists(doc_source_above_threshold, min_size=0, max_size=5),
    nones=st.lists(doc_source_none_score, min_size=1, max_size=5),
)
@h_settings(max_examples=100)
def test_frontend_filter_none_scores_retained(
    above: list[DocumentSource],
    nones: list[DocumentSource],
):
    """**Validates: Requirements 3.3, 3.5**

    Property: When DocumentSource objects have confidence_score = None
    (legacy cached data), the frontend filter retains them.
    Mixed lists with both None and above-threshold scores preserve all entries.
    """
    # Interleave above-threshold and None-scored sources
    combined = above + nones

    filtered = frontend_source_filter(combined)

    assert len(filtered) == len(combined), (
        f"Expected {len(combined)} sources but filter returned {len(filtered)}. "
        f"None-scored sources should be retained for backward compatibility."
    )
    # Verify all None-scored sources are present
    none_in_filtered = [s for s in filtered if s.confidence_score is None]
    assert len(none_in_filtered) == len(nones), (
        f"Expected {len(nones)} None-scored sources but found {len(none_in_filtered)} in filtered list"
    )
