"""
Property-based tests for RAGService region-aware retrieval.

# Feature: i18n-medical-content, Property 11: RAG query includes region filter for non-ALL regions

Validates: Requirements 4.6
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.embedding_service import EmbeddingModel
from backend.services.llm_router import LLMResult, LLMRouter
from backend.services.rag_service import RAGService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NON_ALL_REGIONS = st.sampled_from(["TG", "BJ"])


def _make_service() -> tuple[RAGService, MagicMock]:
    """Return a RAGService and the mock collection so the pipeline can be captured."""
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])

    mock_collection = MagicMock()
    mock_collection.aggregate = MagicMock(return_value=mock_cursor)

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_mongo = MagicMock()
    mock_mongo.__getitem__ = MagicMock(return_value=mock_db)

    embedder = MagicMock(spec=EmbeddingModel)
    embedder.encode = AsyncMock(return_value=[0.1] * 1536)

    llm = MagicMock(spec=LLMRouter)
    llm.generate = AsyncMock(return_value=LLMResult(answer="ok", fallback_used=False))
    llm.last_used = "qwen3"

    service = RAGService(mongo_client=mock_mongo, llm_router=llm, embedder=embedder)
    service._chunks = mock_collection
    return service, mock_collection


def _captured_pipeline(mock_collection: MagicMock) -> list[dict[str, Any]]:
    """Extract the pipeline passed to aggregate()."""
    return mock_collection.aggregate.call_args.args[0]


# ---------------------------------------------------------------------------
# Property 11: RAG query includes region filter for non-ALL regions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@given(region=NON_ALL_REGIONS)
@h_settings(max_examples=100)
async def test_property_11_region_filter_present_for_non_all_regions(region: str) -> None:
    """**Validates: Requirements 4.6**

    For any region R ∈ {"TG", "BJ"}, the $vectorSearch pipeline SHALL include
    a filter on metadata.region restricting results to {R, "ALL"}.
    """
    service, mock_collection = _make_service()

    await service.query("fever treatment", region=region)

    pipeline = _captured_pipeline(mock_collection)
    vs_stage = pipeline[0]["$vectorSearch"]

    assert "filter" in vs_stage, (
        f"Expected 'filter' key in $vectorSearch stage for region={region!r}, "
        f"but got: {vs_stage}"
    )
    region_filter = vs_stage["filter"]["metadata.region"]
    assert "$in" in region_filter, (
        f"Expected '$in' operator in metadata.region filter, got: {region_filter}"
    )
    assert region in region_filter["$in"], (
        f"Expected region {region!r} in $in list, got: {region_filter['$in']}"
    )
    assert "ALL" in region_filter["$in"], (
        f"Expected 'ALL' in $in list, got: {region_filter['$in']}"
    )
    assert region_filter["$in"] == [region, "ALL"], (
        f"Expected $in to be [{region!r}, 'ALL'], got: {region_filter['$in']}"
    )


@pytest.mark.asyncio
async def test_property_11_no_filter_when_region_is_none() -> None:
    """**Validates: Requirements 4.6**

    When region=None, the $vectorSearch pipeline SHALL NOT include a filter.
    """
    service, mock_collection = _make_service()

    await service.query("fever treatment", region=None)

    pipeline = _captured_pipeline(mock_collection)
    vs_stage = pipeline[0]["$vectorSearch"]

    assert "filter" not in vs_stage, (
        f"Expected no 'filter' key in $vectorSearch stage for region=None, "
        f"but got: {vs_stage}"
    )


@pytest.mark.asyncio
async def test_property_11_no_filter_when_region_is_all() -> None:
    """**Validates: Requirements 4.6**

    When region="ALL", the $vectorSearch pipeline SHALL NOT include a filter.
    """
    service, mock_collection = _make_service()

    await service.query("fever treatment", region="ALL")

    pipeline = _captured_pipeline(mock_collection)
    vs_stage = pipeline[0]["$vectorSearch"]

    assert "filter" not in vs_stage, (
        f"Expected no 'filter' key in $vectorSearch stage for region='ALL', "
        f"but got: {vs_stage}"
    )
