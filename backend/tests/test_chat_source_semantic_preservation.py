"""
Preservation property tests — Chat Source Semantic Fix

These tests capture the EXISTING correct behavior for non-buggy paths
(cross-encoder unavailable, empty chunks, region filtering, caching).
They must PASS on unfixed code and continue to pass after the fix.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Property 2: Preservation — Fallback and Non-Reranked Paths Unchanged
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st

from backend.services.index_manager import (
    cross_encoder_rerank,
    filter_by_region,
    filter_by_similarity,
)

# ---------------------------------------------------------------------------
# Hypothesis profile (matches existing bug test pattern)
# ---------------------------------------------------------------------------

h_settings.register_profile(
    "ci",
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
h_settings.load_profile("ci")

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

REGIONS = ["ALL", "TG", "BJ", "SN", "CI"]


def _make_chunk(
    doc_id: str,
    content: str,
    vector_score: float,
    region: str = "ALL",
) -> dict[str, Any]:
    """Build a chunk dict matching the shape used by IndexManager."""
    return {
        "document_id": doc_id,
        "content": content,
        "score": vector_score,
        "metadata": {
            "source": "test",
            "region": region,
            "title": f"Doc {doc_id}",
            "section": None,
            "page": 1,
        },
    }


@st.composite
def chunk_list_without_ce_score(draw):
    """Generate 1-8 chunks with vector scores but NO ce_score field."""
    n = draw(st.integers(min_value=1, max_value=8))
    chunks = []
    for i in range(n):
        score = draw(score_strategy)
        region = draw(st.sampled_from(REGIONS))
        chunks.append(_make_chunk(
            doc_id=f"doc_{i}",
            content=f"Content for chunk {i}",
            vector_score=score,
            region=region,
        ))
    return chunks


@st.composite
def chunk_list_with_region(draw):
    """Generate 2-8 chunks with mixed regions."""
    n = draw(st.integers(min_value=2, max_value=8))
    chunks = []
    for i in range(n):
        score = draw(score_strategy)
        region = draw(st.sampled_from(REGIONS))
        chunks.append(_make_chunk(
            doc_id=f"doc_{i}",
            content=f"Content for chunk {i}",
            vector_score=score,
            region=region,
        ))
    target_region = draw(st.sampled_from(REGIONS))
    return chunks, target_region


# ---------------------------------------------------------------------------
# Property 2.1: cross_encoder_rerank returns chunks unchanged when
#               cross-encoder is unavailable (Req 3.1)
# ---------------------------------------------------------------------------


@given(chunks=chunk_list_without_ce_score())
def test_cross_encoder_rerank_fallback_returns_unchanged(chunks):
    """When the cross-encoder import fails, cross_encoder_rerank must return
    the input list unchanged (identity fallback).

    **Validates: Requirements 3.1**
    """
    with patch(
        "backend.services.document_service.get_cross_encoder",
        side_effect=ImportError("cross-encoder not available"),
    ):
        result = cross_encoder_rerank("any query", chunks)

    # The returned list must be the exact same objects in the same order
    assert len(result) == len(chunks)
    for orig, returned in zip(chunks, result):
        assert orig["document_id"] == returned["document_id"]
        assert orig["score"] == returned["score"]
        # No ce_score should be added in fallback path
        assert "ce_score" not in returned


# ---------------------------------------------------------------------------
# Property 2.2: filter_by_similarity filters by 'score' when no ce_score
#               is present (Req 3.1, 3.5)
# ---------------------------------------------------------------------------


@given(
    chunks=chunk_list_without_ce_score(),
    threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_filter_by_similarity_uses_score_when_no_ce_score(chunks, threshold):
    """When chunks have no ce_score field, filter_by_similarity must filter
    by the 'score' field, retaining chunks where score >= threshold.

    **Validates: Requirements 3.1, 3.5**
    """
    filtered = filter_by_similarity(chunks, threshold=threshold)

    # Manually compute expected result using score field
    expected = [c for c in chunks if c.get("score", 1.0) >= threshold]

    assert len(filtered) == len(expected)
    filtered_ids = [c["document_id"] for c in filtered]
    expected_ids = [c["document_id"] for c in expected]
    assert filtered_ids == expected_ids


# ---------------------------------------------------------------------------
# Property 2.3: Empty chunk retrieval returns sources=[] and
#               confidence_score=None (Req 3.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [
    "What is malaria?",
    "Symptômes de la dengue",
    "Treatment options for tuberculosis",
])
async def test_pipeline_empty_chunks_returns_no_sources(question):
    """When IndexManager.retrieve returns no chunks, the pipeline must return
    a RAGResponse with sources=[] and confidence_score=None.

    **Validates: Requirements 3.2**
    """
    from backend.services.llamaindex_pipeline import LlamaIndexPipeline
    from backend.services.index_manager import IndexManager as _IndexManager

    # Mock IndexManager.retrieve to return empty list
    mock_index = AsyncMock(spec=_IndexManager)
    mock_index.retrieve.return_value = []

    # Mock LLMRouter.generate to return a simple answer
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = MagicMock(
        answer="General medical knowledge answer",
        fallback_used=False,
    )
    mock_llm.last_used = "test-model"

    # Mock EmbeddingModel.encode
    mock_embedder = AsyncMock()
    mock_embedder.encode.return_value = [0.1] * 10

    pipeline = LlamaIndexPipeline(
        index_manager=mock_index,
        llm_router=mock_llm,
        embedder=mock_embedder,
    )

    # Mock cache to return None (cache miss)
    with patch("backend.services.llamaindex_pipeline.cache_service") as mock_cache:
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()
        mock_cache.make_key = MagicMock(return_value="test:rag:key")

        response = await pipeline.query(question)

    assert response.sources == []
    assert response.confidence_score is None
    assert response.answer == "General medical knowledge answer"


# ---------------------------------------------------------------------------
# Property 2.4: Region pre-filtering continues to work (Req 3.3)
# ---------------------------------------------------------------------------


@given(data=chunk_list_with_region())
def test_filter_by_region_preserves_behavior(data):
    """Region pre-filtering must continue to work correctly:
    - region=None or "ALL" returns all chunks
    - specific region returns only chunks matching that region or "ALL"

    **Validates: Requirements 3.3**
    """
    chunks, target_region = data

    filtered = filter_by_region(chunks, target_region)

    if target_region == "ALL" or not target_region:
        # All chunks should pass
        assert len(filtered) == len(chunks)
    else:
        # Only chunks with matching region or "ALL" should pass
        for c in filtered:
            chunk_region = c.get("metadata", {}).get("region", "ALL")
            assert chunk_region in (target_region, "ALL"), (
                f"Chunk with region '{chunk_region}' should not pass "
                f"filter for region '{target_region}'"
            )
        # Verify no matching chunks were dropped
        expected = [
            c for c in chunks
            if c.get("metadata", {}).get("region", "ALL") in (target_region, "ALL")
        ]
        assert len(filtered) == len(expected)


# ---------------------------------------------------------------------------
# Property 2.5: Cached responses returned without re-running retrieval
#               (Req 3.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cached_response_returned_without_retrieval():
    """When a cached RAG response exists, it must be returned directly
    without calling IndexManager.retrieve or LLMRouter.generate.

    **Validates: Requirements 3.4**
    """
    from backend.models.document import RAGResponse
    from backend.services.llamaindex_pipeline import LlamaIndexPipeline
    from backend.services.index_manager import IndexManager as _IndexManager

    cached_response = RAGResponse(
        answer="Cached answer",
        sources=[],
        llm_used="cached-model",
        confidence_score=0.85,
        fallback_used=False,
    )

    mock_index = AsyncMock(spec=_IndexManager)
    mock_llm = AsyncMock()
    mock_embedder = AsyncMock()

    pipeline = LlamaIndexPipeline(
        index_manager=mock_index,
        llm_router=mock_llm,
        embedder=mock_embedder,
    )

    with patch("backend.services.llamaindex_pipeline.cache_service") as mock_cache:
        mock_cache.get = AsyncMock(return_value=cached_response.model_dump_json())
        mock_cache.make_key = MagicMock(return_value="test:rag:key")

        response = await pipeline.query("test question")

    assert response.answer == "Cached answer"
    assert response.llm_used == "cached-model"
    assert response.confidence_score == 0.85

    # Verify retrieve and generate were NOT called
    mock_index.retrieve.assert_not_called()
    mock_llm.generate.assert_not_called()
    mock_embedder.encode.assert_not_called()
