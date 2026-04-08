"""
Property 7: Source relevance filtering

**Validates: Requirements 10.1, 10.3**

Tests that:
1. All sources in result have score >= threshold
2. No source with score >= threshold is excluded
3. When no chunks meet threshold, sources list is empty
"""
from __future__ import annotations

from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Filtering logic under test (mirrors LlamaIndexPipeline.query)
# ---------------------------------------------------------------------------

def _filter_sources_by_threshold(
    sources: list[dict],
    chunks: list[dict],
    threshold: float,
) -> list[dict]:
    """Replicate the source filtering logic from LlamaIndexPipeline.query().

    Req 10.1–10.4: Filter sources by relevance threshold.
    """
    return [
        s for s, c in zip(sources, chunks)
        if float(c.get("ce_score", c.get("score", 0.0))) >= threshold
    ]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_st_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
_st_threshold = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

_st_chunk_with_ce_score = st.fixed_dictionaries({
    "ce_score": _st_score,
    "content": st.text(min_size=1, max_size=50),
})

_st_chunk_with_score = st.fixed_dictionaries({
    "score": _st_score,
    "content": st.text(min_size=1, max_size=50),
})

_st_chunk = st.one_of(_st_chunk_with_ce_score, _st_chunk_with_score)

_st_chunks = st.lists(_st_chunk, min_size=0, max_size=20)


# ---------------------------------------------------------------------------
# Property 7.1 — All retained sources have score >= threshold
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    chunks=_st_chunks,
    threshold=_st_threshold,
)
def test_property_7_all_retained_above_threshold(
    chunks: list[dict],
    threshold: float,
) -> None:
    """**Validates: Requirements 10.1**

    Every source in the filtered result has a chunk score >= threshold.
    """
    sources = [{"id": i} for i in range(len(chunks))]
    filtered = _filter_sources_by_threshold(sources, chunks, threshold)

    for s in filtered:
        idx = s["id"]
        c = chunks[idx]
        score = float(c.get("ce_score", c.get("score", 0.0)))
        assert score >= threshold, (
            f"Source {idx} has score {score} < threshold {threshold}"
        )


# ---------------------------------------------------------------------------
# Property 7.2 — No qualifying source is excluded
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    chunks=_st_chunks,
    threshold=_st_threshold,
)
def test_property_7_no_qualifying_source_excluded(
    chunks: list[dict],
    threshold: float,
) -> None:
    """**Validates: Requirements 10.1, 10.3**

    No source with score >= threshold is missing from the filtered result.
    """
    sources = [{"id": i} for i in range(len(chunks))]
    filtered = _filter_sources_by_threshold(sources, chunks, threshold)
    filtered_ids = {s["id"] for s in filtered}

    for i, c in enumerate(chunks):
        score = float(c.get("ce_score", c.get("score", 0.0)))
        if score >= threshold:
            assert i in filtered_ids, (
                f"Source {i} with score {score} >= threshold {threshold} was excluded"
            )


# ---------------------------------------------------------------------------
# Property 7.3 — Empty result when no chunks meet threshold
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    threshold=_st_threshold,
)
def test_property_7_empty_when_none_qualify(
    threshold: float,
) -> None:
    """**Validates: Requirements 10.3**

    When no chunks meet the threshold, the filtered sources list is empty.
    """
    from hypothesis import assume
    assume(threshold > 0.0)

    # All chunks have score 0.0, which is below any positive threshold
    chunks = [{"score": 0.0, "content": "text"} for _ in range(5)]
    sources = [{"id": i} for i in range(len(chunks))]
    filtered = _filter_sources_by_threshold(sources, chunks, threshold)

    assert len(filtered) == 0, (
        f"Expected empty result but got {len(filtered)} sources"
    )
