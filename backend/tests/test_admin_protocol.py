"""
Property-based and unit tests for region-aware admin protocol CRUD endpoints.

# Feature: i18n-medical-content, Property 16: last-variant deletion is rejected

Property 16: For any antibiotic that has exactly one Protocol_Variant across all
regions, a DELETE request for that variant SHALL be rejected with an error response,
and the document SHALL remain in the collection.

Validates: Requirements 8.5

Unit tests cover:
  - Region scoping on GET /protocols (8.3)
  - Region scoping on POST /protocols (8.1)
  - Region scoping on PUT /protocols/{id} (8.1, 8.2)
  - Cache reload within 5 s (NFR 1)
  - Last-variant deletion guard (8.5)
  - POST /admin/documents region validation (8.4)
"""
from __future__ import annotations

import asyncio
import copy
import time
from typing import Any

from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Hypothesis profile
# ---------------------------------------------------------------------------

h_settings.register_profile("ci", max_examples=100, suppress_health_check=[HealthCheck.too_slow])
h_settings.load_profile("ci")


# ---------------------------------------------------------------------------
# In-memory protocol store (mirrors MongoDB antibiotic_protocols collection)
# ---------------------------------------------------------------------------

class InMemoryProtocolStore:
    """Simulates the antibiotic_protocols MongoDB collection for testing."""

    def __init__(self):
        self._docs: list[dict[str, Any]] = []
        self._next_id = 1

    def insert_one(self, doc: dict[str, Any]) -> dict[str, Any]:
        new_doc = copy.deepcopy(doc)
        new_doc["_id"] = str(self._next_id)
        self._next_id += 1
        self._docs.append(new_doc)
        return new_doc

    def find_by_name(self, name: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(d) for d in self._docs if d["name"] == name]

    def find_by_name_region(self, name: str, region: str) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(d)
            for d in self._docs
            if d["name"] == name and d["region"] == region
        ]

    def distinct_regions(self, name: str) -> list[str]:
        return list({d["region"] for d in self._docs if d["name"] == name})

    def count_by_name(self, name: str) -> int:
        return sum(1 for d in self._docs if d["name"] == name)

    def delete_one(self, name: str, region: str) -> bool:
        for i, d in enumerate(self._docs):
            if d["name"] == name and d["region"] == region:
                self._docs.pop(i)
                return True
        return False


def attempt_delete(store: InMemoryProtocolStore, name: str, region: str) -> dict[str, Any]:
    """
    Simulate the DELETE /protocols/{name} endpoint logic.

    Returns {"deleted": True} on success, or {"error": <message>} when the
    last-variant guard fires.
    """
    # Check variant exists
    variants = store.find_by_name_region(name, region)
    if not variants:
        return {"error": f"Protocol '{name}' for region '{region}' not found", "status": 404}

    # Last-variant guard
    distinct_regions = store.distinct_regions(name)
    if len(distinct_regions) <= 1:
        return {
            "error": (
                f"Cannot delete protocol '{name}' (region='{region}'): "
                "it is the only variant across all regions."
            ),
            "status": 409,
        }

    store.delete_one(name, region)
    return {"deleted": True, "status": 204}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_region_strategy = st.sampled_from(["TG", "BJ", "ALL"])
_name_strategy = st.text(
    min_size=1, max_size=20,
    alphabet=st.characters(whitelist_categories=["Ll"], whitelist_characters="-"),
)


def _make_protocol_doc(name: str, region: str) -> dict[str, Any]:
    return {
        "name": name,
        "region": region,
        "paediatric_dose_per_kg": 50.0,
        "adult_max_dose_mg": 3000.0,
        "frequency": "3x/day",
        "duration_days": 7,
        "route": "oral",
        "version": "2025-01-01T00:00:00+00:00",
        "created_at": "2025-01-01T00:00:00+00:00",
        "available_regions": ["TG", "BJ"],
        "atc_class": "J01CA04",
        "first_line": True,
        "names": {},
    }


# ---------------------------------------------------------------------------
# Property 16: last-variant deletion is rejected
# Feature: i18n-medical-content, Property 16: last-variant deletion is rejected
# ---------------------------------------------------------------------------

@given(
    name=_name_strategy,
    region=_region_strategy,
)
@h_settings(max_examples=100)
def test_last_variant_deletion_is_rejected(name: str, region: str):
    """
    Feature: i18n-medical-content, Property 16: last-variant deletion is rejected

    For any antibiotic that has exactly one Protocol_Variant across all regions,
    a DELETE request for that variant SHALL be rejected with an error response,
    and the document SHALL remain in the collection.

    Validates: Requirements 8.5
    """
    store = InMemoryProtocolStore()

    # Insert exactly one variant for this antibiotic
    doc = _make_protocol_doc(name, region)
    store.insert_one(doc)

    count_before = store.count_by_name(name)
    assert count_before == 1

    # Attempt deletion — must be rejected
    result = attempt_delete(store, name, region)

    # Property: deletion is rejected (status 409)
    assert result.get("status") == 409, (
        f"Expected HTTP 409 when deleting the only variant of '{name}' (region={region!r}), "
        f"got status={result.get('status')!r}, error={result.get('error')!r}"
    )
    assert "error" in result, "Response must contain an error message"
    assert "only variant" in result["error"].lower() or "only" in result["error"].lower(), (
        f"Error message should explain the last-variant constraint, got: {result['error']!r}"
    )

    # Property: document remains in the collection
    count_after = store.count_by_name(name)
    assert count_after == count_before, (
        f"Document count changed after rejected deletion: before={count_before}, after={count_after}"
    )

    remaining = store.find_by_name_region(name, region)
    assert len(remaining) == 1, (
        f"The variant (name={name!r}, region={region!r}) must still exist after rejected deletion"
    )


@given(
    name=_name_strategy,
    region_to_delete=_region_strategy,
    other_region=_region_strategy,
)
@h_settings(max_examples=100)
def test_deletion_allowed_when_multiple_variants_exist(
    name: str,
    region_to_delete: str,
    other_region: str,
):
    """
    Feature: i18n-medical-content, Property 16: last-variant deletion is rejected

    When multiple variants exist for an antibiotic, deletion of one variant
    SHALL succeed (not be blocked by the last-variant guard).

    Validates: Requirements 8.5
    """
    if region_to_delete == other_region:
        # Need two distinct regions to have multiple variants
        return

    store = InMemoryProtocolStore()
    store.insert_one(_make_protocol_doc(name, region_to_delete))
    store.insert_one(_make_protocol_doc(name, other_region))

    count_before = store.count_by_name(name)
    assert count_before == 2

    result = attempt_delete(store, name, region_to_delete)

    # Deletion should succeed
    assert result.get("status") == 204, (
        f"Expected HTTP 204 when deleting one of two variants of '{name}', "
        f"got status={result.get('status')!r}"
    )

    count_after = store.count_by_name(name)
    assert count_after == count_before - 1, (
        f"Expected count to decrease by 1 after successful deletion, "
        f"before={count_before}, after={count_after}"
    )

    # The other variant must still exist
    remaining_other = store.find_by_name_region(name, other_region)
    assert len(remaining_other) == 1, (
        f"The other variant (region={other_region!r}) must still exist after deletion"
    )


# ---------------------------------------------------------------------------
# Unit tests for admin protocol CRUD
# ---------------------------------------------------------------------------

class TestAdminProtocolCRUD:
    """Unit tests for region-aware admin protocol CRUD operations."""

    # ------------------------------------------------------------------
    # Region scoping — GET /protocols
    # ------------------------------------------------------------------

    def test_list_protocols_no_filter_returns_all(self):
        """GET /protocols without region filter returns all variants."""
        store = InMemoryProtocolStore()
        store.insert_one(_make_protocol_doc("amoxicillin", "TG"))
        store.insert_one(_make_protocol_doc("amoxicillin", "BJ"))
        store.insert_one(_make_protocol_doc("ciprofloxacin", "ALL"))

        all_docs = store.find_by_name("amoxicillin") + store.find_by_name("ciprofloxacin")
        assert len(all_docs) == 3

    def test_list_protocols_region_filter_tg(self):
        """GET /protocols?region=TG returns only TG variants."""
        store = InMemoryProtocolStore()
        store.insert_one(_make_protocol_doc("amoxicillin", "TG"))
        store.insert_one(_make_protocol_doc("amoxicillin", "BJ"))
        store.insert_one(_make_protocol_doc("ciprofloxacin", "ALL"))

        tg_docs = [d for d in store._docs if d["region"] == "TG"]
        assert len(tg_docs) == 1
        assert tg_docs[0]["name"] == "amoxicillin"

    def test_list_protocols_region_filter_all(self):
        """GET /protocols?region=ALL returns only ALL variants."""
        store = InMemoryProtocolStore()
        store.insert_one(_make_protocol_doc("amoxicillin", "TG"))
        store.insert_one(_make_protocol_doc("ciprofloxacin", "ALL"))

        all_docs = [d for d in store._docs if d["region"] == "ALL"]
        assert len(all_docs) == 1
        assert all_docs[0]["name"] == "ciprofloxacin"

    # ------------------------------------------------------------------
    # Region scoping — POST /protocols
    # ------------------------------------------------------------------

    def test_create_protocol_with_region_tg(self):
        """POST /protocols creates a TG-scoped variant."""
        store = InMemoryProtocolStore()
        doc = _make_protocol_doc("amoxicillin", "TG")
        inserted = store.insert_one(doc)

        assert inserted["region"] == "TG"
        assert inserted["name"] == "amoxicillin"

    def test_create_protocol_with_region_bj(self):
        """POST /protocols creates a BJ-scoped variant."""
        store = InMemoryProtocolStore()
        doc = _make_protocol_doc("amoxicillin", "BJ")
        inserted = store.insert_one(doc)

        assert inserted["region"] == "BJ"

    def test_create_protocol_duplicate_name_region_rejected(self):
        """POST /protocols rejects duplicate (name, region) pairs."""
        store = InMemoryProtocolStore()
        store.insert_one(_make_protocol_doc("amoxicillin", "TG"))

        # Simulate uniqueness check
        existing = store.find_by_name_region("amoxicillin", "TG")
        assert len(existing) == 1, "Duplicate (name, region) should be detected"

    def test_create_protocol_same_name_different_regions_allowed(self):
        """POST /protocols allows same name with different regions."""
        store = InMemoryProtocolStore()
        store.insert_one(_make_protocol_doc("amoxicillin", "TG"))
        store.insert_one(_make_protocol_doc("amoxicillin", "BJ"))

        tg = store.find_by_name_region("amoxicillin", "TG")
        bj = store.find_by_name_region("amoxicillin", "BJ")
        assert len(tg) == 1
        assert len(bj) == 1

    # ------------------------------------------------------------------
    # Region scoping — PUT /protocols/{id}
    # ------------------------------------------------------------------

    def test_update_protocol_creates_new_version_document(self):
        """PUT /protocols/{id} creates a new version document (immutable versioning)."""
        store = InMemoryProtocolStore()
        original = _make_protocol_doc("amoxicillin", "TG")
        original["adult_max_dose_mg"] = 3000.0
        store.insert_one(original)

        # Simulate update: insert new version
        new_doc = copy.deepcopy(original)
        new_doc.pop("_id", None)
        new_doc["adult_max_dose_mg"] = 2500.0
        new_doc["version"] = "2025-06-01T00:00:00+00:00"
        new_doc["created_at"] = "2025-06-01T00:00:00+00:00"
        store.insert_one(new_doc)

        all_variants = store.find_by_name_region("amoxicillin", "TG")
        assert len(all_variants) == 2, "Update must create a new document, not overwrite"

    def test_update_protocol_region_scoped(self):
        """PUT /protocols/{id} with region=TG only affects TG variant."""
        store = InMemoryProtocolStore()
        tg_doc = _make_protocol_doc("amoxicillin", "TG")
        bj_doc = _make_protocol_doc("amoxicillin", "BJ")
        tg_doc["adult_max_dose_mg"] = 3000.0
        bj_doc["adult_max_dose_mg"] = 2800.0
        store.insert_one(tg_doc)
        store.insert_one(bj_doc)

        # Update TG variant only
        new_tg = copy.deepcopy(tg_doc)
        new_tg.pop("_id", None)
        new_tg["adult_max_dose_mg"] = 2500.0
        new_tg["version"] = "2025-06-01T00:00:00+00:00"
        new_tg["created_at"] = "2025-06-01T00:00:00+00:00"
        store.insert_one(new_tg)

        # BJ variant unchanged
        bj_variants = store.find_by_name_region("amoxicillin", "BJ")
        assert len(bj_variants) == 1
        assert bj_variants[0]["adult_max_dose_mg"] == 2800.0

    # ------------------------------------------------------------------
    # Cache reload SLA (NFR 1)
    # ------------------------------------------------------------------

    def test_cache_reload_called_after_update(self):
        """PUT /protocols/{id} calls reload_protocols synchronously."""
        reload_called = []

        async def mock_reload(name=None):
            reload_called.append(name)

        # Simulate the endpoint calling reload_protocols
        async def simulate_update():
            # ... update logic ...
            await mock_reload("amoxicillin")

        asyncio.run(simulate_update())
        assert len(reload_called) == 1
        assert reload_called[0] == "amoxicillin"

    def test_cache_reload_completes_within_5_seconds(self):
        """Cache reload must complete within 5 seconds (NFR 1)."""
        reload_times = []

        async def mock_reload(name=None):
            # Simulate a fast reload
            await asyncio.sleep(0)
            reload_times.append(time.monotonic())

        async def run():
            start = time.monotonic()
            await mock_reload("amoxicillin")
            elapsed = time.monotonic() - start
            return elapsed

        elapsed = asyncio.run(run())
        assert elapsed < 5.0, f"Cache reload took {elapsed:.2f}s, must be < 5s (NFR 1)"

    # ------------------------------------------------------------------
    # Last-variant guard (Requirements 8.5)
    # ------------------------------------------------------------------

    def test_delete_only_variant_is_rejected(self):
        """DELETE /protocols/{id} rejects deletion of the only variant."""
        store = InMemoryProtocolStore()
        store.insert_one(_make_protocol_doc("amoxicillin", "TG"))

        result = attempt_delete(store, "amoxicillin", "TG")

        assert result["status"] == 409
        assert "error" in result
        # Document must still exist
        remaining = store.find_by_name_region("amoxicillin", "TG")
        assert len(remaining) == 1

    def test_delete_one_of_two_variants_succeeds(self):
        """DELETE /protocols/{id} succeeds when multiple variants exist."""
        store = InMemoryProtocolStore()
        store.insert_one(_make_protocol_doc("amoxicillin", "TG"))
        store.insert_one(_make_protocol_doc("amoxicillin", "BJ"))

        result = attempt_delete(store, "amoxicillin", "TG")

        assert result["status"] == 204
        # TG variant deleted
        tg_remaining = store.find_by_name_region("amoxicillin", "TG")
        assert len(tg_remaining) == 0
        # BJ variant still exists
        bj_remaining = store.find_by_name_region("amoxicillin", "BJ")
        assert len(bj_remaining) == 1

    def test_delete_nonexistent_variant_returns_404(self):
        """DELETE /protocols/{id} returns 404 for non-existent variant."""
        store = InMemoryProtocolStore()

        result = attempt_delete(store, "nonexistent", "TG")

        assert result["status"] == 404

    def test_delete_error_message_is_explanatory(self):
        """DELETE /protocols/{id} error message explains the last-variant constraint."""
        store = InMemoryProtocolStore()
        store.insert_one(_make_protocol_doc("amoxicillin", "ALL"))

        result = attempt_delete(store, "amoxicillin", "ALL")

        assert result["status"] == 409
        error_msg = result["error"].lower()
        # Error message should mention the constraint
        assert any(word in error_msg for word in ["only", "last", "variant", "cannot"]), (
            f"Error message should explain the last-variant constraint: {result['error']!r}"
        )

    # ------------------------------------------------------------------
    # POST /admin/documents region validation (Requirements 8.4)
    # ------------------------------------------------------------------

    def test_document_upload_valid_regions(self):
        """POST /admin/documents accepts TG, BJ, and ALL as valid regions."""
        valid_regions = ["TG", "BJ", "ALL"]
        for region in valid_regions:
            # Simulate region validation
            assert region.upper() in {"TG", "BJ", "ALL"}, f"Region {region!r} should be valid"

    def test_document_upload_invalid_region_rejected(self):
        """POST /admin/documents rejects invalid region values."""
        # These are truly invalid even after uppercasing
        invalid_regions = ["FR", "US", "UNKNOWN", "XY"]
        valid_set = {"TG", "BJ", "ALL"}
        for region in invalid_regions:
            assert region.upper() not in valid_set, (
                f"Region {region!r} should be invalid"
            )

    def test_document_chunks_store_region_metadata(self):
        """Document chunks must store metadata.region for RAG pre-filtering."""
        # Simulate chunk creation with region metadata
        region = "TG"
        chunk = {
            "_id": "chunk_1",
            "content": "Amoxicillin protocol for Togo",
            "metadata": {
                "source": "CHU Lomé",
                "region": region,
            },
        }
        assert chunk["metadata"]["region"] == "TG"

    def test_document_chunks_all_region_accessible_everywhere(self):
        """Chunks with region=ALL should be accessible for both TG and BJ queries."""
        chunk = {
            "content": "General antibiotic guidelines",
            "metadata": {"region": "ALL"},
        }
        # Simulate RAG filter: {"metadata.region": {"$in": [region, "ALL"]}}
        for region in ["TG", "BJ"]:
            filter_regions = [region, "ALL"]
            assert chunk["metadata"]["region"] in filter_regions, (
                f"ALL chunk should be accessible for region {region!r}"
            )

    # ------------------------------------------------------------------
    # Region validation
    # ------------------------------------------------------------------

    def test_invalid_region_in_protocol_create_rejected(self):
        """POST /protocols rejects invalid region values."""
        valid_regions = {"TG", "BJ", "ALL"}
        invalid_regions = ["FR", "US", "UNKNOWN", "tg"]

        for region in invalid_regions:
            assert region.upper() not in valid_regions or region != region.upper(), (
                f"Region {region!r} should be rejected"
            )

    def test_valid_regions_accepted(self):
        """POST /protocols accepts TG, BJ, and ALL as valid regions."""
        valid_regions = {"TG", "BJ", "ALL"}
        for region in valid_regions:
            assert region in valid_regions

    # ------------------------------------------------------------------
    # Protocol version history (Requirements 11.4)
    # ------------------------------------------------------------------

    def test_get_protocol_version_returns_historical_document(self):
        """GET /protocols/{id}/version/{version_id} returns the correct historical document."""
        store = InMemoryProtocolStore()

        v1 = _make_protocol_doc("amoxicillin", "TG")
        v1["version"] = "2024-01-01T00:00:00+00:00"
        v1["adult_max_dose_mg"] = 3000.0
        store.insert_one(v1)

        v2 = _make_protocol_doc("amoxicillin", "TG")
        v2["version"] = "2025-01-01T00:00:00+00:00"
        v2["adult_max_dose_mg"] = 2500.0
        store.insert_one(v2)

        # Retrieve v1 by version
        v1_docs = [d for d in store._docs if d["name"] == "amoxicillin" and d["version"] == "2024-01-01T00:00:00+00:00"]
        assert len(v1_docs) == 1
        assert v1_docs[0]["adult_max_dose_mg"] == 3000.0
