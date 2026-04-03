"""
Property-based tests for admin router — Migration par lots de 100 chunks maximum.

# Feature: diagno-pilot-improvements, Property 17: Migration par lots de 100 chunks maximum
"""
from __future__ import annotations

import asyncio
import math
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Hypothesis profile
# ---------------------------------------------------------------------------

h_settings.register_profile("ci", max_examples=100, suppress_health_check=[HealthCheck.too_slow])
h_settings.load_profile("ci")


# ---------------------------------------------------------------------------
# Property 17: Migration par lots de 100 chunks maximum
# Feature: diagno-pilot-improvements, Property 17: Migration par lots de 100 chunks maximum
# ---------------------------------------------------------------------------

def _make_fake_chunk(i: int) -> dict:
    """Create a fake unmigrated chunk (missing enriched metadata fields)."""
    return {
        "_id": f"chunk_{i}",
        "content": f"Chunk content {i}",
        "metadata": {
            "source": "CHU Lomé",
            # Intentionally missing: disease_tags, document_type, evidence_level
        },
    }


@given(st.integers(min_value=0, max_value=500))
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_17_migration_batch_size(n: int):
    """
    Feature: diagno-pilot-improvements, Property 17: Migration par lots de 100 chunks maximum

    For any number N of unmigrated chunks, _migrate_chunks_background must process
    them in exactly ⌈N/100⌉ batches of at most 100 chunks each.

    Validates: Requirements 6.2
    """
    from backend.routers.admin import _migrate_chunks_background

    batch_size = 100
    expected_batches = math.ceil(n / batch_size) if n > 0 else 0

    # Build the list of fake chunks
    all_chunks = [_make_fake_chunk(i) for i in range(n)]

    # Track how many times find().limit(100) was called with non-empty results
    find_limit_call_count = 0

    def make_cursor(batch_chunks):
        """Return a mock cursor whose to_list returns the given batch."""
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=batch_chunks)
        return cursor

    def make_find_mock():
        """
        Returns a mock for database["document_chunks"].find(...).
        Each call to .limit(100) returns the next batch of chunks,
        then an empty list to signal end-of-migration.
        """
        nonlocal find_limit_call_count

        # Precompute batches
        batches = []
        for start in range(0, n, batch_size):
            batches.append(all_chunks[start : start + batch_size])
        # Final empty batch to terminate the loop
        batches.append([])

        call_index = [0]

        def find_side_effect(*args, **kwargs):
            """Called each time database["document_chunks"].find(...) is invoked."""
            find_mock = MagicMock()

            def limit_side_effect(size):
                nonlocal find_limit_call_count
                idx = call_index[0]
                call_index[0] += 1
                batch = batches[idx] if idx < len(batches) else []
                if batch:
                    find_limit_call_count += 1
                return make_cursor(batch)

            find_mock.limit = MagicMock(side_effect=limit_side_effect)
            return find_mock

        return find_side_effect

    # Build mock collection
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(side_effect=make_find_mock())
    mock_collection.update_one = AsyncMock(return_value=None)

    # Build mock database
    mock_database = MagicMock()
    mock_database.__getitem__ = MagicMock(return_value=mock_collection)

    # Patch infer_document_type and DISEASE_KEYWORDS used inside _migrate_chunks_background
    with patch(
        "backend.services.document_service.infer_document_type",
        return_value="guideline",
    ), patch(
        "backend.services.document_service.DISEASE_KEYWORDS",
        new=set(),
    ):
        asyncio.run(_migrate_chunks_background(mock_database))

    # Assert: number of non-empty batches processed == ⌈N/100⌉
    assert find_limit_call_count == expected_batches, (
        f"Expected ⌈{n}/100⌉ = {expected_batches} non-empty batch(es), "
        f"but got {find_limit_call_count} batch call(s) for N={n}"
    )
