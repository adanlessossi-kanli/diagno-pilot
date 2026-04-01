"""Tests for RAGService degraded-mode behaviour.

Tests cover:
  Property 6 — Vector search failure triggers degraded_warning round-trip
  Property 7 — Keyword fallback respects top_k
  Unit test  — Embedding exception propagation without fallback
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from backend.services.embedding_service import EmbeddingModel
from backend.services.llm_router import LLMResult, LLMRouter
from backend.services.rag_service import RAGService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _make_chunk(content: str = "Some medical content.") -> dict:
    return {
        "document_id": "doc1",
        "content": content,
        "metadata": {"source": "CHU_LOME", "section": "General"},
    }


def _make_rag_service(
    *,
    vector_search_raises: Exception | None = None,
    keyword_chunks: list[dict] | None = None,
    llm_answer: str = "Generated answer.",
    llm_fallback_used: bool = False,
) -> RAGService:
    """Build a RAGService with mocked dependencies.

    - If vector_search_raises is set, the first aggregate call raises that exception.
    - keyword_chunks controls what the keyword fallback returns (default: []).
    """
    if keyword_chunks is None:
        keyword_chunks = []

    # Build a mock collection whose aggregate() behaves differently on first vs second call.
    mock_collection = MagicMock()

    if vector_search_raises is not None:
        # First call ($vectorSearch) raises; second call ($text) returns keyword_chunks.
        keyword_cursor = MagicMock()
        keyword_cursor.to_list = AsyncMock(return_value=keyword_chunks)

        def _aggregate_side_effect(pipeline):
            stage = pipeline[0]
            if "$vectorSearch" in stage:
                raise vector_search_raises
            # keyword fallback pipeline
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=keyword_chunks)
            return cursor

        mock_collection.aggregate = MagicMock(side_effect=_aggregate_side_effect)
    else:
        # Normal path: vector search returns empty list (no chunks needed for these tests)
        normal_cursor = MagicMock()
        normal_cursor.to_list = AsyncMock(return_value=[])
        mock_collection.aggregate = MagicMock(return_value=normal_cursor)

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    mock_mongo = MagicMock()
    mock_mongo.__getitem__ = MagicMock(return_value=mock_db)

    embedder = MagicMock(spec=EmbeddingModel)
    embedder.encode = AsyncMock(return_value=[0.1] * 1536)

    llm = MagicMock(spec=LLMRouter)
    llm.generate = AsyncMock(return_value=LLMResult(answer=llm_answer, fallback_used=llm_fallback_used))
    llm.last_used = "gpt5" if llm_fallback_used else "qwen3"

    service = RAGService(mongo_client=mock_mongo, llm_router=llm, embedder=embedder)
    service._chunks = mock_collection
    return service


# ---------------------------------------------------------------------------
# Property 6: Vector search failure triggers degraded_warning round-trip
# Feature: llm-resilience, Property 6: Vector search failure triggers degraded_warning round-trip
# ---------------------------------------------------------------------------

@given(
    error_message=st.text(min_size=1, max_size=100),
    keyword_content=st.lists(
        st.text(min_size=1, max_size=50),
        min_size=1,
        max_size=5,
    ),
)
@h_settings(max_examples=100, deadline=None)
def test_vector_search_failure_sets_degraded_warning(
    error_message: str, keyword_content: list[str]
) -> None:
    """For any $vectorSearch exception with keyword fallback returning results,
    RAGResponse.degraded_warning SHALL be non-None.

    # Feature: llm-resilience, Property 6: Vector search failure triggers degraded_warning round-trip
    Validates: Requirements 2.1, 2.2, 2.6
    """
    keyword_chunks = [_make_chunk(content=c) for c in keyword_content]
    service = _make_rag_service(
        vector_search_raises=RuntimeError(error_message),
        keyword_chunks=keyword_chunks,
    )

    async def _test():
        response = await service.query("test question")
        assert response.degraded_warning is not None, (
            "degraded_warning must be non-None when $vectorSearch fails and keyword fallback returns results"
        )
        assert "Vector Search unavailable" in response.degraded_warning

    _run(_test())


@given(
    error_message=st.text(min_size=1, max_size=100),
    keyword_content=st.lists(
        st.text(min_size=1, max_size=50),
        min_size=1,
        max_size=5,
    ),
)
@h_settings(max_examples=100, deadline=None)
def test_vector_search_failure_degraded_warning_propagates_to_response(
    error_message: str, keyword_content: list[str]
) -> None:
    """The degraded_warning value on RAGResponse is the canonical warning string.

    # Feature: llm-resilience, Property 6: Vector search failure triggers degraded_warning round-trip
    Validates: Requirements 2.1, 2.2, 2.6
    """
    keyword_chunks = [_make_chunk(content=c) for c in keyword_content]
    service = _make_rag_service(
        vector_search_raises=Exception(error_message),
        keyword_chunks=keyword_chunks,
    )

    async def _test():
        response = await service.query("clinical question")
        expected = "Vector Search unavailable — response based on keyword retrieval only"
        assert response.degraded_warning == expected, (
            f"Expected degraded_warning={expected!r}, got {response.degraded_warning!r}"
        )

    _run(_test())


# ---------------------------------------------------------------------------
# Property 7: Keyword fallback respects top_k
# Feature: llm-resilience, Property 7: Keyword fallback respects top_k
# ---------------------------------------------------------------------------

@given(top_k=st.integers(min_value=1, max_value=20))
@h_settings(max_examples=100, deadline=None)
def test_keyword_fallback_respects_top_k(top_k: int) -> None:
    """When keyword fallback is triggered, the $text query limit SHALL equal top_k.

    # Feature: llm-resilience, Property 7: Keyword fallback respects top_k
    Validates: Requirements 2.8
    """
    keyword_chunks = [_make_chunk() for _ in range(min(top_k, 3))]
    service = _make_rag_service(
        vector_search_raises=RuntimeError("vector search down"),
        keyword_chunks=keyword_chunks,
    )

    # Track the pipelines passed to aggregate
    aggregate_calls: list[list] = []
    original_aggregate = service._chunks.aggregate

    def _tracking_aggregate(pipeline):
        aggregate_calls.append(pipeline)
        return original_aggregate(pipeline)

    service._chunks.aggregate = MagicMock(side_effect=_tracking_aggregate)

    async def _test():
        await service.query("test question", top_k=top_k)

        # Find the keyword fallback pipeline call (the one with $match/$text)
        keyword_pipelines = [
            p for p in aggregate_calls
            if p and "$match" in p[0] and "$text" in p[0].get("$match", {})
        ]
        assert len(keyword_pipelines) >= 1, (
            "Expected at least one keyword fallback pipeline call"
        )
        keyword_pipeline = keyword_pipelines[0]

        # Find the $limit stage
        limit_stages = [stage for stage in keyword_pipeline if "$limit" in stage]
        assert len(limit_stages) == 1, (
            f"Expected exactly one $limit stage in keyword pipeline, got: {keyword_pipeline}"
        )
        assert limit_stages[0]["$limit"] == top_k, (
            f"Expected $limit={top_k}, got {limit_stages[0]['$limit']}"
        )

    _run(_test())


# ---------------------------------------------------------------------------
# Unit test: Embedding exception propagation without fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embedding_exception_propagates_without_fallback():
    """An exception from EmbeddingModel.encode propagates to the caller unchanged.

    Validates: Requirements 2.7
    """
    service = _make_rag_service()
    embed_error = RuntimeError("Embedding service unavailable")
    service._embedder.encode = AsyncMock(side_effect=embed_error)

    with pytest.raises(RuntimeError) as exc_info:
        await service.query("test question")

    assert exc_info.value is embed_error, (
        "The exact exception from EmbeddingModel.encode must propagate unchanged"
    )
    # LLM must NOT have been called
    service._llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_embedding_exception_does_not_trigger_vector_search():
    """When EmbeddingModel.encode raises, no MongoDB aggregate call is made.

    Validates: Requirements 2.7
    """
    service = _make_rag_service()
    service._embedder.encode = AsyncMock(side_effect=ValueError("bad input"))

    with pytest.raises(ValueError):
        await service.query("test question")

    service._chunks.aggregate.assert_not_called()
