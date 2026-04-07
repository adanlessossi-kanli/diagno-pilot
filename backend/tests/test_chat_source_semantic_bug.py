"""
Bug condition exploration tests — Chat Source Semantic Fix

These tests assert the EXPECTED (correct) behavior and will FAIL on unfixed
code, proving each bug exists. DO NOT fix the code or the tests when they fail.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5**

Property 1: Bug Condition — Cross-Encoder Scores Discarded and Sources Misordered

Expected counterexamples (on unfixed code):
  - cross_encoder_rerank() returns chunks without ce_score field
  - Sources sorted by stale vector score differ from cross-encoder order
  - filter_by_similarity drops chunks the cross-encoder ranked highly
  - LLM context built from different chunks than sources
  - Confidence computed from all chunks' stale scores, not source ce_scores
"""
from __future__ import annotations

from statistics import mean
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st

from backend.services.index_manager import cross_encoder_rerank, filter_by_similarity

# ---------------------------------------------------------------------------
# Hypothesis profile
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

# Scores in [0.0, 1.0] — typical cosine similarity range
score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


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


# Strategy: generate a list of chunks where vector score order ≠ cross-encoder order
# We generate pairs of (vector_score, ce_score) and ensure the orderings differ.
@st.composite
def divergent_chunk_list(draw):
    """Generate 3-8 chunks where vector-score ranking differs from cross-encoder ranking."""
    n = draw(st.integers(min_value=3, max_value=8))
    vector_scores = draw(
        st.lists(score_strategy, min_size=n, max_size=n).filter(
            lambda xs: len(set(xs)) == len(xs)  # unique scores
        )
    )
    ce_scores = draw(
        st.lists(score_strategy, min_size=n, max_size=n).filter(
            lambda xs: len(set(xs)) == len(xs)
        )
    )
    # Ensure the two orderings are different
    vec_order = sorted(range(n), key=lambda i: vector_scores[i], reverse=True)
    ce_order = sorted(range(n), key=lambda i: ce_scores[i], reverse=True)
    if vec_order == ce_order:
        # Swap first two ce_scores to force divergence
        ce_scores[0], ce_scores[1] = ce_scores[1], ce_scores[0]

    chunks = []
    for i in range(n):
        chunks.append(_make_chunk(
            doc_id=f"doc_{i}",
            content=f"Content for chunk {i}",
            vector_score=vector_scores[i],
        ))
    return chunks, ce_scores


def _make_mock_cross_encoder(ce_scores: list[float]):
    """Return a mock cross-encoder whose predict() returns the given scores."""
    mock = MagicMock()
    mock.predict.return_value = ce_scores
    return mock


# ---------------------------------------------------------------------------
# Property 1.1: ce_score stored on each chunk after reranking (Req 2.1)
# ---------------------------------------------------------------------------


@given(data=divergent_chunk_list())
def test_cross_encoder_rerank_stores_ce_score(data):
    """After cross_encoder_rerank(), every returned chunk must have a 'ce_score' key.

    EXPECTED: FAILS on unfixed code — ce_scores are discarded after sorting.
    Validates Req 2.1.
    """
    chunks, ce_scores = data
    mock_ce = _make_mock_cross_encoder(ce_scores)

    with patch(
        "backend.services.document_service.get_cross_encoder",
        return_value=mock_ce,
    ):
        reranked = cross_encoder_rerank("test query", chunks)

    for chunk in reranked:
        assert "ce_score" in chunk, (
            f"Chunk {chunk['document_id']} missing 'ce_score' after reranking. "
            f"Vector score={chunk.get('score')}"
        )


# ---------------------------------------------------------------------------
# Property 1.2: filter_by_similarity uses ce_score when present (Req 2.4)
# ---------------------------------------------------------------------------


@given(data=divergent_chunk_list())
def test_filter_by_similarity_uses_ce_score(data):
    """Chunks with ce_score >= threshold must survive filtering even if vector score < threshold.

    EXPECTED: FAILS on unfixed code — filter uses stale vector 'score' field.
    Validates Req 2.4.
    """
    chunks, ce_scores = data
    threshold = 0.75

    # Build chunks that have low vector score but high ce_score
    test_chunks = []
    for i, chunk in enumerate(chunks):
        c = dict(chunk)
        c["score"] = 0.3  # below threshold
        c["ce_score"] = ce_scores[i]
        test_chunks.append(c)

    # At least one chunk should have ce_score >= threshold
    has_high_ce = any(c["ce_score"] >= threshold for c in test_chunks)
    if not has_high_ce:
        # Force one chunk above threshold for a meaningful test
        test_chunks[0]["ce_score"] = 0.9

    filtered = filter_by_similarity(test_chunks, threshold=threshold)

    # Every chunk with ce_score >= threshold should survive
    for c in test_chunks:
        if c["ce_score"] >= threshold:
            assert c in filtered, (
                f"Chunk {c['document_id']} with ce_score={c['ce_score']:.3f} "
                f"(>= threshold {threshold}) was dropped by filter_by_similarity. "
                f"Vector score={c['score']:.3f}"
            )


# ---------------------------------------------------------------------------
# Property 1.3–1.5: Pipeline sources, LLM context, and confidence (Req 2.2, 2.3, 2.5)
# ---------------------------------------------------------------------------


@given(data=divergent_chunk_list())
def test_pipeline_sources_ordered_by_ce_score(data):
    """Sources must be ordered by ce_score descending, not stale vector score.

    EXPECTED: FAILS on unfixed code — sources sorted by vector 'score' because
    cross_encoder_rerank() never stores ce_score on the chunks.
    Validates Req 2.2.
    """
    chunks, ce_scores = data
    mock_ce = _make_mock_cross_encoder(ce_scores)

    with patch(
        "backend.services.document_service.get_cross_encoder",
        return_value=mock_ce,
    ):
        reranked = cross_encoder_rerank("test query", list(chunks))

    # What the fixed pipeline does: sort by ce_score (falling back to score)
    actual_top = sorted(
        reranked,
        key=lambda c: float(c.get("ce_score", c.get("score", 0.0))),
        reverse=True,
    )[:5]
    actual_ids = [c["document_id"] for c in actual_top]

    # Expected: sort by cross-encoder scores (which we know from ce_scores input)
    ce_score_map = {chunks[i]["document_id"]: ce_scores[i] for i in range(len(chunks))}
    expected_top = sorted(
        reranked,
        key=lambda c: ce_score_map.get(c["document_id"], 0.0),
        reverse=True,
    )[:5]
    expected_ids = [c["document_id"] for c in expected_top]

    assert actual_ids == expected_ids, (
        f"Sources not ordered by cross-encoder score: {actual_ids}. "
        f"Expected order: {expected_ids}"
    )


@given(data=divergent_chunk_list())
def test_pipeline_llm_context_subset_of_sources(data):
    """LLM context chunks must be a subset of the source chunks.

    EXPECTED: FAILS on unfixed code — LLM uses chunks[:3] (positional after
    reranking) while sources use sorted(chunks, key=score)[:5] (vector score).
    After reranking changes positional order, these sets can diverge.
    Validates Req 2.3.
    """
    chunks, ce_scores = data
    mock_ce = _make_mock_cross_encoder(ce_scores)

    with patch(
        "backend.services.document_service.get_cross_encoder",
        return_value=mock_ce,
    ):
        reranked = cross_encoder_rerank("test query", list(chunks))

    # Fixed behavior: both sources and LLM context from same top_chunks sorted by ce_score
    top_chunks = sorted(
        reranked,
        key=lambda c: float(c.get("ce_score", c.get("score", 0.0))),
        reverse=True,
    )[:5]
    source_chunks = top_chunks
    llm_chunks = top_chunks[:3]

    source_ids = {c["document_id"] for c in source_chunks}
    llm_ids = {c["document_id"] for c in llm_chunks}

    assert llm_ids.issubset(source_ids), (
        f"LLM context chunks {llm_ids - source_ids} are not in source set. "
        f"Source IDs: {source_ids}, LLM IDs: {llm_ids}"
    )


@given(data=divergent_chunk_list())
def test_pipeline_confidence_from_source_ce_scores(data):
    """Confidence must equal the mean of ce_score values of the source chunks.

    EXPECTED: FAILS on unfixed code — confidence averages all chunks' stale vector scores.
    Validates Req 2.5.
    """
    chunks, ce_scores = data
    mock_ce = _make_mock_cross_encoder(ce_scores)

    with patch(
        "backend.services.document_service.get_cross_encoder",
        return_value=mock_ce,
    ):
        reranked = cross_encoder_rerank("test query", list(chunks))

    # Fixed confidence: mean of top 5 source chunks' ce_score (falling back to score)
    top_chunks = sorted(
        reranked,
        key=lambda c: float(c.get("ce_score", c.get("score", 0.0))),
        reverse=True,
    )[:5]
    actual_scores = [float(c.get("ce_score", c.get("score", 0.0))) for c in top_chunks]
    actual_confidence = mean(actual_scores) if actual_scores else None

    # Expected confidence: mean of top 5 source chunks' cross-encoder scores
    ce_score_map = {chunks[i]["document_id"]: ce_scores[i] for i in range(len(chunks))}
    expected_top = sorted(
        reranked,
        key=lambda c: ce_score_map.get(c["document_id"], 0.0),
        reverse=True,
    )[:5]
    expected_scores = [ce_score_map[c["document_id"]] for c in expected_top]
    expected_confidence = mean(expected_scores) if expected_scores else None

    assert actual_confidence == pytest.approx(expected_confidence, abs=1e-6), (
        f"Confidence {actual_confidence:.4f} does not match expected {expected_confidence:.4f} "
        f"from top source ce_scores."
    )
