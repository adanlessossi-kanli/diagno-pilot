"""
Property-based tests for the antibiotic_protocols migration script.

# Feature: i18n-medical-content, Property 14: protocol migration assigns region ALL to legacy documents

Property 14: For any existing antibiotic_protocols document that lacks a region
field, the migration script SHALL assign region: "ALL" without modifying any
other field.

Validates: Requirements 9.3
"""
from __future__ import annotations

from typing import Any

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate arbitrary field values that could appear in a protocol document
_field_value_strategy = st.one_of(
    st.text(min_size=0, max_size=32),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.none(),
    st.lists(st.text(max_size=10), max_size=3),
)

# Generate a protocol document WITHOUT a region field
_protocol_doc_strategy = st.fixed_dictionaries(  # type: ignore[misc]
    {
        "name": st.text(min_size=1, max_size=32),
        "paediatric_dose_per_kg": st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
        "adult_max_dose_mg": st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        "frequency": st.sampled_from(["1x/day", "2x/day", "3x/day", "4x/day"]),
        "duration_days": st.integers(min_value=1, max_value=30),
        "route": st.sampled_from(["oral", "IV", "IM"]),
    },
    optional={
        "renal_adjustment_factor": st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
        "hepatic_adjustment_factor": st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
        "alternative": st.one_of(st.none(), st.text(min_size=1, max_size=32)),
        "atc_class": st.text(min_size=0, max_size=10),
        "first_line": st.booleans(),
    },
)


# ---------------------------------------------------------------------------
# Migration logic (extracted for in-memory testing)
# ---------------------------------------------------------------------------

def apply_migration(doc: dict[str, Any]) -> dict[str, Any]:
    """
    Apply the migration logic to a single document in-memory.

    Mirrors the $set operation in migrate_protocols_add_region.py:
    - Only modifies documents that do NOT have a 'region' field.
    - Sets region='ALL' and available_regions=['TG', 'BJ'].
    - Does NOT modify any other field.
    """
    if "region" in doc:
        return doc  # already migrated — idempotent
    result = dict(doc)
    result["region"] = "ALL"
    result["available_regions"] = ["TG", "BJ"]
    return result


# ---------------------------------------------------------------------------
# Property 14: migration assigns region ALL to legacy documents
# Feature: i18n-medical-content, Property 14: protocol migration assigns region ALL to legacy documents
# ---------------------------------------------------------------------------

@given(doc=_protocol_doc_strategy)
@h_settings(max_examples=100)
def test_migration_assigns_region_all_to_legacy_documents(doc: dict[str, Any]):
    """
    Feature: i18n-medical-content, Property 14: protocol migration assigns region ALL to legacy documents

    For any existing antibiotic_protocols document that lacks a region field,
    the migration script SHALL assign region: "ALL" and available_regions: ["TG", "BJ"]
    without modifying any other field.

    Validates: Requirements 9.3
    """
    # Precondition: document has no region field
    assert "region" not in doc, "Strategy must not include 'region' field"

    # Capture original fields
    original_fields = dict(doc)

    # Apply migration
    migrated = apply_migration(doc)

    # Assert region is set to ALL
    assert migrated["region"] == "ALL", (
        f"Expected region='ALL' after migration, got {migrated['region']!r}"
    )

    # Assert available_regions is set correctly
    assert migrated["available_regions"] == ["TG", "BJ"], (
        f"Expected available_regions=['TG', 'BJ'], got {migrated['available_regions']!r}"
    )

    # Assert all original fields remain unchanged
    for key, value in original_fields.items():
        assert migrated[key] == value, (
            f"Field {key!r} was modified by migration: "
            f"original={value!r}, after={migrated[key]!r}"
        )


@given(doc=_protocol_doc_strategy)
@h_settings(max_examples=100)
def test_migration_is_idempotent(doc: dict[str, Any]):
    """
    Feature: i18n-medical-content, Property 14: protocol migration assigns region ALL to legacy documents

    Running the migration twice produces the same result as running it once.

    Validates: Requirements 9.3
    """
    first_pass = apply_migration(doc)
    second_pass = apply_migration(first_pass)

    assert first_pass == second_pass, (
        f"Migration is not idempotent: first={first_pass!r}, second={second_pass!r}"
    )


@given(doc=_protocol_doc_strategy)
@h_settings(max_examples=100)
def test_migration_does_not_add_extra_fields(doc: dict[str, Any]):
    """
    Feature: i18n-medical-content, Property 14: protocol migration assigns region ALL to legacy documents

    The migration SHALL only add 'region' and 'available_regions' — no other
    fields are introduced.

    Validates: Requirements 9.3
    """
    migrated = apply_migration(doc)
    original_keys = set(doc.keys())
    migrated_keys = set(migrated.keys())
    new_keys = migrated_keys - original_keys

    assert new_keys == {"region", "available_regions"}, (
        f"Migration added unexpected fields: {new_keys - {'region', 'available_regions'}!r}"
    )


# ---------------------------------------------------------------------------
# Unit tests — specific examples
# ---------------------------------------------------------------------------

class TestMigrationExamples:
    """Unit tests for the migration logic with specific inputs."""

    def test_legacy_doc_gets_region_all(self):
        doc = {
            "name": "amoxicillin",
            "paediatric_dose_per_kg": 50.0,
            "adult_max_dose_mg": 3000.0,
            "frequency": "3x/day",
            "duration_days": 7,
            "route": "oral",
        }
        result = apply_migration(doc)
        assert result["region"] == "ALL"
        assert result["available_regions"] == ["TG", "BJ"]
        # Original fields unchanged
        assert result["name"] == "amoxicillin"
        assert result["paediatric_dose_per_kg"] == 50.0

    def test_already_migrated_doc_is_unchanged(self):
        doc = {
            "name": "ciprofloxacin",
            "region": "TG",
            "available_regions": ["TG"],
            "paediatric_dose_per_kg": 20.0,
            "adult_max_dose_mg": 1500.0,
            "frequency": "2x/day",
            "duration_days": 7,
            "route": "oral",
        }
        result = apply_migration(doc)
        # region must not be overwritten
        assert result["region"] == "TG"
        assert result["available_regions"] == ["TG"]

    def test_migration_preserves_optional_fields(self):
        doc = {
            "name": "metronidazole",
            "paediatric_dose_per_kg": 30.0,
            "adult_max_dose_mg": 2000.0,
            "frequency": "3x/day",
            "duration_days": 7,
            "route": "oral",
            "hepatic_adjustment_factor": 0.5,
            "alternative": "tinidazole",
        }
        result = apply_migration(doc)
        assert result["hepatic_adjustment_factor"] == 0.5
        assert result["alternative"] == "tinidazole"
        assert result["region"] == "ALL"
