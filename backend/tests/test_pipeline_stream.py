"""Unit tests for LlamaIndexPipeline.query_stream().

Validates: Requirements 3.1, 3.4
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.document import RAGResponse
from backend.services.llamaindex_pipeline import LlamaIndexPipeline, StreamEvent
from backend.services.llm_router import StreamChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_pipeline(router_chunks: list[StreamChunk], chunks: list[dict] | None = None):
    """Create a LlamaIndexPipeline with mocked dependencies.

    Args:
        router_chunks: StreamChunks the mocked LLMRouter.generate_stream yields.
        chunks: Retrieval results from IndexManager.retrieve. Defaults to [].
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
# Test: Retrieval + streaming integration
# ---------------------------------------------------------------------------


def test_retrieval_and_streaming_integration():
    """Retrieval returns chunks, LLM streams tokens — yields token events
    followed by a done event with correct sources and metadata."""
    mock_chunks = [
        {
            "document_id": "doc-1",
            "metadata": {"title": "Malaria Guide", "source": "WHO", "section": "Treatment"},
            "content": "Artemisinin-based combination therapy is recommended.",
            "ce_score": 0.95,
        },
        {
            "document_id": "doc-2",
            "metadata": {"title": "Fever Protocol", "source": "MSF", "section": "Diagnosis"},
            "content": "Rapid diagnostic tests should be used.",
            "ce_score": 0.88,
        },
    ]

    router_chunks = [
        StreamChunk(token="The ", llm_used="test-model"),
        StreamChunk(token="answer ", llm_used="test-model"),
        StreamChunk(token="is here.", llm_used="test-model"),
    ]

    pipeline = _make_pipeline(router_chunks, chunks=mock_chunks)

    async def run():
        events: list[StreamEvent] = []
        with patch("backend.services.llamaindex_pipeline.cache_service") as mock_cache, \
             patch("backend.services.llamaindex_pipeline.settings") as mock_settings:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_cache.make_key = MagicMock(return_value="test-key")
            mock_settings.SOURCE_RELEVANCE_THRESHOLD = 0.0
            mock_settings.CACHE_TTL_RAG = 300
            async for event in pipeline.query_stream("What is the treatment?"):
                events.append(event)
        return events, mock_cache

    events, _ = _run(run())

    # Token events
    token_events = [e for e in events if e.type == "token"]
    assert len(token_events) == 3
    assert token_events[0].content == "The "
    assert token_events[1].content == "answer "
    assert token_events[2].content == "is here."

    # Done event
    done_events = [e for e in events if e.type == "done"]
    assert len(done_events) == 1
    done = done_events[0]
    assert done.answer == "The answer is here."
    assert done.llm_used == "test-model"
    assert done.fallback_used is False
    assert done.confidence_score is not None

    # Sources in done event
    assert done.sources is not None
    assert len(done.sources) == 2
    assert done.sources[0].document_id == "doc-1"
    assert done.sources[0].title == "Malaria Guide"
    assert done.sources[0].source == "WHO"
    assert done.sources[1].document_id == "doc-2"


# ---------------------------------------------------------------------------
# Test: Cache write after completion
# ---------------------------------------------------------------------------


def test_cache_write_after_streaming_completion():
    """After streaming completes, cache_service.set() is called with the
    correct cache key and a serialised RAGResponse containing the
    accumulated answer."""
    router_chunks = [
        StreamChunk(token="cached ", llm_used="primary-model"),
        StreamChunk(token="response", llm_used="primary-model"),
    ]

    pipeline = _make_pipeline(router_chunks)

    captured_cache_set_args = {}

    async def run():
        with patch("backend.services.llamaindex_pipeline.cache_service") as mock_cache, \
             patch("backend.services.llamaindex_pipeline.settings") as mock_settings:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.make_key = MagicMock(return_value="rag:test-key")
            mock_settings.SOURCE_RELEVANCE_THRESHOLD = 0.0
            mock_settings.CACHE_TTL_RAG = 300

            async def capture_set(key, value, ttl):
                captured_cache_set_args["key"] = key
                captured_cache_set_args["value"] = value
                captured_cache_set_args["ttl"] = ttl

            mock_cache.set = AsyncMock(side_effect=capture_set)

            async for _ in pipeline.query_stream("test question"):
                pass

    _run(run())

    # Verify cache was written
    assert "key" in captured_cache_set_args, "cache_service.set() was not called"
    assert captured_cache_set_args["key"] == "rag:test-key"
    assert captured_cache_set_args["ttl"] == 300

    # Verify the cached value is a valid RAGResponse
    cached_response = RAGResponse.model_validate_json(captured_cache_set_args["value"])
    assert cached_response.answer == "cached response"
    assert cached_response.llm_used == "primary-model"
    assert cached_response.fallback_used is False


# ---------------------------------------------------------------------------
# Test: Error event on retrieval failure
# ---------------------------------------------------------------------------


def test_error_event_on_retrieval_failure():
    """When EmbeddingModel.encode() raises, query_stream() yields a
    StreamEvent(type='error') with retryable=True."""
    pipeline = LlamaIndexPipeline.__new__(LlamaIndexPipeline)

    # Mock EmbeddingModel to raise
    embedder = MagicMock()
    embedder.encode = AsyncMock(side_effect=RuntimeError("Embedding service down"))
    pipeline._embedder = embedder

    # Mock IndexManager (should not be reached)
    index = MagicMock()
    index.retrieve = AsyncMock(return_value=[])
    pipeline._index = index

    # Mock LLMRouter (should not be reached)
    router = MagicMock()
    router.last_used = "unused"
    pipeline._llm = router

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

    assert len(events) == 1
    assert events[0].type == "error"
    assert "Embedding service down" in events[0].error
    assert events[0].retryable is True

    # IndexManager.retrieve should not have been called
    index.retrieve.assert_not_called()


def test_error_event_on_index_retrieve_failure():
    """When IndexManager.retrieve() raises, query_stream() yields a
    StreamEvent(type='error') with retryable=True."""
    pipeline = LlamaIndexPipeline.__new__(LlamaIndexPipeline)

    # Mock EmbeddingModel (succeeds)
    embedder = MagicMock()
    embedder.encode = AsyncMock(return_value=[0.0] * 128)
    pipeline._embedder = embedder

    # Mock IndexManager to raise
    index = MagicMock()
    index.retrieve = AsyncMock(side_effect=ConnectionError("MongoDB unavailable"))
    pipeline._index = index

    # Mock LLMRouter (should not be reached)
    router = MagicMock()
    router.last_used = "unused"
    pipeline._llm = router

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

    assert len(events) == 1
    assert events[0].type == "error"
    assert "MongoDB unavailable" in events[0].error
    assert events[0].retryable is True
