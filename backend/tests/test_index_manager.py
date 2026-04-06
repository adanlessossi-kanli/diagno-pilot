"""
Property tests for IndexManager — Diagno-Pilot

# Feature: llm-llamaindex-hipaa-refactor, Properties 6 & 7

**Validates: Requirements 4.4, 4.6**
"""
from __future__ import annotations

from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.services.index_manager import filter_by_region, filter_by_similarity

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Scores in [0.0, 1.0] — typical cosine similarity range
score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Threshold in a reasonable range
threshold_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Regions used in the project
region_strategy = st.sampled_from(["TG", "BJ", "ALL"])

# A chunk dict with a score and region metadata
def chunk_strategy(
    score_st=score_strategy,
    region_st=region_strategy,
):
    return st.fixed_dictionaries(
        {
            "content": st.text(min_size=1, max_size=50),
            "document_id": st.text(min_size=1, max_size=10),
            "metadata": st.fixed_dictionaries(
                {
                    "source": st.just("test"),
                    "region": region_st,
                }
            ),
        },
        optional={"score": score_st},
    )


chunks_strategy = st.lists(chunk_strategy(), min_size=0, max_size=30)


# ---------------------------------------------------------------------------
# Property 6: Similarity threshold filter
# ---------------------------------------------------------------------------


@given(chunks=chunks_strategy, threshold=threshold_strategy)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_6_similarity_threshold_filter(
    chunks: list[dict], threshold: float
):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 6: Similarity threshold filter
    **Validates: Requirements 4.4**

    For any list of scored retrieval results, applying the similarity threshold
    filter SHALL return only results with score >= threshold, and all results
    with score >= threshold SHALL be retained.
    """
    result = filter_by_similarity(chunks, threshold=threshold)

    for chunk in result:
        # Every returned chunk must have score >= threshold (or no score at all)
        score = chunk.get("score", 1.0)
        assert score >= threshold, (
            f"Chunk with score {score} should have been filtered at threshold {threshold}"
        )

    # Every chunk in the original list that meets the threshold must be present
    expected_ids = {
        c["document_id"]
        for c in chunks
        if c.get("score", 1.0) >= threshold
    }
    result_ids = {c["document_id"] for c in result}
    missing = expected_ids - result_ids
    assert not missing, f"Chunks that should have passed the filter are missing: {missing}"


# ---------------------------------------------------------------------------
# Property 7: Region filter correctness
# ---------------------------------------------------------------------------


@given(
    chunks=chunks_strategy,
    target_region=st.sampled_from(["TG", "BJ", "ALL", None]),
)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_7_region_filter_correctness(
    chunks: list[dict], target_region: str | None
):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 7: Region filter correctness
    **Validates: Requirements 4.6**

    For any set of document chunks with region metadata and any target region,
    applying the region filter SHALL return only chunks whose region matches
    the target region or is "ALL".
    """
    result = filter_by_region(chunks, target_region)

    if not target_region or target_region == "ALL":
        # No filtering — all chunks should pass
        assert len(result) == len(chunks), (
            f"Expected all {len(chunks)} chunks when region is {target_region!r}, "
            f"got {len(result)}"
        )
    else:
        for chunk in result:
            chunk_region = chunk.get("metadata", {}).get("region", "ALL")
            assert chunk_region in (target_region, "ALL"), (
                f"Chunk with region {chunk_region!r} should not pass "
                f"filter for target region {target_region!r}"
            )

        # All matching chunks from the original list must be present
        expected_count = sum(
            1
            for c in chunks
            if c.get("metadata", {}).get("region", "ALL") in (target_region, "ALL")
        )
        assert len(result) == expected_count, (
            f"Expected {expected_count} chunks for region {target_region!r}, "
            f"got {len(result)}"
        )
