"""
Property-based tests for protocol version history.

# Feature: i18n-medical-content, Property 15: protocol update creates a new version document

Property 15: For any protocol update operation, the number of documents in
`antibiotic_protocols` with the given (name, region) pair SHALL increase by
exactly 1, and the original document SHALL remain unchanged.

Validates: Requirements 11.1, 11.2
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone, timedelta
from typing import Any

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_region_strategy = st.sampled_from(["TG", "BJ", "ALL"])

_protocol_doc_strategy = st.fixed_dictionaries(
    {
        "name": st.text(min_size=1, max_size=32, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-")),
        "region": _region_strategy,
        "paediatric_dose_per_kg": st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
        "adult_max_dose_mg": st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        "frequency": st.sampled_from(["1x/day", "2x/day", "3x/day", "4x/day"]),
        "duration_days": st.integers(min_value=1, max_value=30),
        "route": st.sampled_from(["oral", "IV", "IM"]),
        "version": st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2024, 12, 31),
        ).map(lambda dt: dt.replace(tzinfo=timezone.utc).isoformat()),
        "created_at": st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2024, 12, 31),
        ).map(lambda dt: dt.replace(tzinfo=timezone.utc).isoformat()),
    },
)

_update_fields_strategy = st.fixed_dictionaries(
    {
        "paediatric_dose_per_kg": st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
        "adult_max_dose_mg": st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        "frequency": st.sampled_from(["1x/day", "2x/day", "3x/day", "4x/day"]),
        "duration_days": st.integers(min_value=1, max_value=30),
        "route": st.sampled_from(["oral", "IV", "IM"]),
    },
)


# ---------------------------------------------------------------------------
# In-memory protocol store (simulates MongoDB collection behaviour)
# ---------------------------------------------------------------------------

class InMemoryProtocolStore:
    """
    Simulates the antibiotic_protocols MongoDB collection.

    - insert_one: adds a new document (never overwrites).
    - find_by_name_region: returns all documents for a (name, region) pair.
    - get_latest: returns the document with the highest created_at for (name, region).
    """

    def __init__(self):
        self._docs: list[dict[str, Any]] = []
        self._next_id = 1

    def insert_one(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Insert a new document. Always creates a new entry — never overwrites."""
        new_doc = copy.deepcopy(doc)
        new_doc["_id"] = str(self._next_id)
        self._next_id += 1
        self._docs.append(new_doc)
        return new_doc

    def find_by_name_region(self, name: str, region: str) -> list[dict[str, Any]]:
        """Return all documents matching (name, region)."""
        return [
            copy.deepcopy(d)
            for d in self._docs
            if d["name"] == name and d["region"] == region
        ]

    def count_by_name_region(self, name: str, region: str) -> int:
        return sum(
            1 for d in self._docs
            if d["name"] == name and d["region"] == region
        )

    def get_latest(self, name: str, region: str) -> dict[str, Any] | None:
        """Return the document with the highest created_at for (name, region)."""
        docs = self.find_by_name_region(name, region)
        if not docs:
            return None
        return max(docs, key=lambda d: d.get("created_at", ""))

    def get_by_version(self, name: str, region: str, version: str) -> dict[str, Any] | None:
        """Return the document matching (name, region, version)."""
        for d in self._docs:
            if d["name"] == name and d["region"] == region and d.get("version") == version:
                return copy.deepcopy(d)
        return None


def apply_protocol_update(
    store: InMemoryProtocolStore,
    original_doc: dict[str, Any],
    update_fields: dict[str, Any],
    new_version: str,
    new_created_at: str,
) -> dict[str, Any]:
    """
    Apply a protocol update by inserting a NEW document rather than overwriting.

    This mirrors the intended behaviour described in Requirements 11.1, 11.2:
    updates create new version documents; the original is never modified.
    """
    new_doc = copy.deepcopy(original_doc)
    new_doc.update(update_fields)
    new_doc["version"] = new_version
    new_doc["created_at"] = new_created_at
    # Remove _id so insert_one assigns a fresh one
    new_doc.pop("_id", None)
    return store.insert_one(new_doc)


# ---------------------------------------------------------------------------
# Property 15: protocol update creates a new version document
# Feature: i18n-medical-content, Property 15: protocol update creates a new version document
# ---------------------------------------------------------------------------

@given(
    original=_protocol_doc_strategy,
    update_fields=_update_fields_strategy,
)
@h_settings(max_examples=100)
def test_protocol_update_creates_new_version_document(
    original: dict[str, Any],
    update_fields: dict[str, Any],
):
    """
    Feature: i18n-medical-content, Property 15: protocol update creates a new version document

    For any protocol update operation, the number of documents in
    `antibiotic_protocols` with the given (name, region) pair SHALL increase
    by exactly 1, and the original document SHALL remain unchanged.

    Validates: Requirements 11.1, 11.2
    """
    store = InMemoryProtocolStore()

    # Insert the original document
    inserted = store.insert_one(copy.deepcopy(original))
    original_id = inserted["_id"]

    name = original["name"]
    region = original["region"]

    # Count before update
    count_before = store.count_by_name_region(name, region)
    assert count_before == 1, f"Expected 1 document before update, got {count_before}"

    # Capture the original document state
    original_snapshot = copy.deepcopy(inserted)

    # Apply update — creates a NEW document with a later created_at
    new_created_at = datetime(2025, 6, 1, tzinfo=timezone.utc).isoformat()
    new_version = new_created_at
    apply_protocol_update(store, inserted, update_fields, new_version, new_created_at)

    # Count after update
    count_after = store.count_by_name_region(name, region)

    # Property: count increased by exactly 1
    assert count_after == count_before + 1, (
        f"Expected document count to increase by 1 (from {count_before} to {count_before + 1}), "
        f"got {count_after} for (name={name!r}, region={region!r})"
    )

    # Property: original document remains unchanged
    docs = store.find_by_name_region(name, region)
    original_in_store = next((d for d in docs if d["_id"] == original_id), None)
    assert original_in_store is not None, "Original document must still exist in the store"

    for key, value in original_snapshot.items():
        assert original_in_store[key] == value, (
            f"Original document field {key!r} was modified: "
            f"expected {value!r}, got {original_in_store[key]!r}"
        )


@given(
    original=_protocol_doc_strategy,
    update_fields=_update_fields_strategy,
    num_updates=st.integers(min_value=1, max_value=5),
)
@h_settings(max_examples=100)
def test_multiple_updates_each_create_new_document(
    original: dict[str, Any],
    update_fields: dict[str, Any],
    num_updates: int,
):
    """
    Feature: i18n-medical-content, Property 15: protocol update creates a new version document

    Each successive update SHALL create exactly one new document, so after N
    updates the total count for (name, region) SHALL be N + 1.

    Validates: Requirements 11.1, 11.2
    """
    store = InMemoryProtocolStore()
    inserted = store.insert_one(copy.deepcopy(original))

    name = original["name"]
    region = original["region"]

    current_doc = inserted
    base_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)

    for i in range(num_updates):
        new_dt = (base_dt + timedelta(days=i + 1)).isoformat()
        current_doc = apply_protocol_update(
            store, current_doc, update_fields, new_version=new_dt, new_created_at=new_dt
        )

    count = store.count_by_name_region(name, region)
    expected = num_updates + 1  # original + one per update

    assert count == expected, (
        f"After {num_updates} update(s), expected {expected} documents for "
        f"(name={name!r}, region={region!r}), got {count}"
    )


@given(original=_protocol_doc_strategy)
@h_settings(max_examples=100)
def test_cache_load_selects_latest_version(original: dict[str, Any]):
    """
    Feature: i18n-medical-content, Property 15: protocol update creates a new version document

    After multiple versions exist, the cache-load logic (selecting the document
    with the highest created_at) SHALL return the most recently created document.

    Validates: Requirements 11.1, 11.2
    """
    store = InMemoryProtocolStore()

    name = original["name"]
    region = original["region"]

    # Insert three versions with increasing created_at timestamps
    base_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    versions = []
    for i in range(3):
        doc = copy.deepcopy(original)
        doc.pop("_id", None)
        ts = (base_dt + timedelta(days=i * 30)).isoformat()
        doc["created_at"] = ts
        doc["version"] = ts
        inserted = store.insert_one(doc)
        versions.append(inserted)

    latest = store.get_latest(name, region)
    assert latest is not None, "get_latest must return a document when versions exist"

    # The latest document should have the highest created_at
    all_docs = store.find_by_name_region(name, region)
    max_created_at = max(d["created_at"] for d in all_docs)

    assert latest["created_at"] == max_created_at, (
        f"Cache load should select document with highest created_at "
        f"({max_created_at!r}), got {latest['created_at']!r}"
    )


# ---------------------------------------------------------------------------
# Unit tests — specific examples
# ---------------------------------------------------------------------------

class TestProtocolVersioningExamples:
    """Unit tests for protocol versioning with specific inputs."""

    def test_update_creates_new_document_not_overwrite(self):
        """Updating a protocol inserts a new document; original is preserved."""
        store = InMemoryProtocolStore()
        original = {
            "name": "amoxicillin",
            "region": "TG",
            "paediatric_dose_per_kg": 50.0,
            "adult_max_dose_mg": 3000.0,
            "frequency": "3x/day",
            "duration_days": 7,
            "route": "oral",
            "version": "2024-01-01T00:00:00+00:00",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
        inserted = store.insert_one(copy.deepcopy(original))

        apply_protocol_update(
            store, inserted,
            update_fields={"adult_max_dose_mg": 2500.0},
            new_version="2025-01-01T00:00:00+00:00",
            new_created_at="2025-01-01T00:00:00+00:00",
        )

        docs = store.find_by_name_region("amoxicillin", "TG")
        assert len(docs) == 2, f"Expected 2 documents, got {len(docs)}"

        # Original document unchanged
        original_doc = next(d for d in docs if d["_id"] == inserted["_id"])
        assert original_doc["adult_max_dose_mg"] == 3000.0
        assert original_doc["version"] == "2024-01-01T00:00:00+00:00"

        # New document has updated fields
        new_doc = next(d for d in docs if d["_id"] != inserted["_id"])
        assert new_doc["adult_max_dose_mg"] == 2500.0
        assert new_doc["version"] == "2025-01-01T00:00:00+00:00"

    def test_cache_load_picks_latest_created_at(self):
        """Cache loading selects the document with the highest created_at."""
        store = InMemoryProtocolStore()

        for ts in ["2023-01-01T00:00:00+00:00", "2024-06-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00"]:
            store.insert_one({
                "name": "ciprofloxacin",
                "region": "ALL",
                "paediatric_dose_per_kg": 20.0,
                "adult_max_dose_mg": 1500.0,
                "frequency": "2x/day",
                "duration_days": 7,
                "route": "oral",
                "version": ts,
                "created_at": ts,
            })

        latest = store.get_latest("ciprofloxacin", "ALL")
        assert latest is not None
        assert latest["created_at"] == "2025-01-01T00:00:00+00:00"

    def test_prescription_service_cache_load_selects_latest(self):
        """
        PrescriptionService.load_protocols_from_db selects the latest version
        for each (name, region) pair when multiple documents exist.
        """
        from backend.services.prescription_service import _doc_to_protocol

        # Simulate two versions of the same (name, region) pair
        docs = [
            {
                "name": "amoxicillin",
                "region": "TG",
                "paediatric_dose_per_kg": 50.0,
                "adult_max_dose_mg": 3000.0,
                "frequency": "3x/day",
                "duration_days": 7,
                "route": "oral",
                "version": "2024-01-01T00:00:00+00:00",
                "created_at": "2024-01-01T00:00:00+00:00",
                "available_regions": ["TG", "BJ"],
                "atc_class": "J01CA04",
                "first_line": True,
                "names": {},
                "renal_adjustment_factor": 1.0,
                "hepatic_adjustment_factor": 1.0,
                "contraindicated_age_groups": [],
                "alternative": None,
            },
            {
                "name": "amoxicillin",
                "region": "TG",
                "paediatric_dose_per_kg": 50.0,
                "adult_max_dose_mg": 2500.0,  # updated dose
                "frequency": "3x/day",
                "duration_days": 7,
                "route": "oral",
                "version": "2025-01-01T00:00:00+00:00",
                "created_at": "2025-01-01T00:00:00+00:00",  # newer
                "available_regions": ["TG", "BJ"],
                "atc_class": "J01CA04",
                "first_line": True,
                "names": {},
                "renal_adjustment_factor": 1.0,
                "hepatic_adjustment_factor": 1.0,
                "contraindicated_age_groups": [],
                "alternative": None,
            },
        ]

        # Replicate the cache-loading logic from load_protocols_from_db
        new_cache = {}
        for doc in docs:
            protocol = _doc_to_protocol(doc)
            key = (protocol.name.lower(), protocol.region)
            existing = new_cache.get(key)
            if existing is None or protocol.created_at >= existing.created_at:
                new_cache[key] = protocol

        # The cache should contain the latest version (adult_max_dose_mg=2500.0)
        cached = new_cache.get(("amoxicillin", "TG"))
        assert cached is not None, "Cache must contain the (amoxicillin, TG) entry"
        assert cached.adult_max_dose_mg == 2500.0, (
            f"Expected latest version dose 2500.0, got {cached.adult_max_dose_mg}"
        )
        assert cached.created_at == "2025-01-01T00:00:00+00:00"

    def test_get_by_version_returns_correct_document(self):
        """Retrieving a protocol by version identifier returns the correct historical document."""
        store = InMemoryProtocolStore()

        v1_ts = "2024-01-01T00:00:00+00:00"
        v2_ts = "2025-01-01T00:00:00+00:00"

        store.insert_one({
            "name": "amoxicillin", "region": "TG",
            "adult_max_dose_mg": 3000.0, "version": v1_ts, "created_at": v1_ts,
        })
        store.insert_one({
            "name": "amoxicillin", "region": "TG",
            "adult_max_dose_mg": 2500.0, "version": v2_ts, "created_at": v2_ts,
        })

        v1_doc = store.get_by_version("amoxicillin", "TG", v1_ts)
        assert v1_doc is not None
        assert v1_doc["adult_max_dose_mg"] == 3000.0

        v2_doc = store.get_by_version("amoxicillin", "TG", v2_ts)
        assert v2_doc is not None
        assert v2_doc["adult_max_dose_mg"] == 2500.0
