"""
Tests de propriété pour la classification PHI — Diagno-Pilot

# Feature: llm-llamaindex-hipaa-refactor, Property 8: PHI classification correctness

**Validates: Requirements 6.1, 6.2, 6.5**

Propriété 8 : Pour tout nom de champ, le PHI_Classifier retourne True pour
les champs PHI connus, False pour les champs non-PHI connus, et True pour
tout champ inconnu (défaut sécuritaire).
"""
from __future__ import annotations

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.phi_classifier import PHIClassifier

classifier = PHIClassifier()

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Known PHI field names (Req 6.1, 6.2)
phi_field_strategy = st.sampled_from(sorted(PHIClassifier.PHI_FIELDS))

# Known non-PHI field names (Req 6.4)
non_phi_field_strategy = st.sampled_from(sorted(PHIClassifier.NON_PHI_FIELDS))

# Unknown field names — generated strings that are NOT in either known set
_all_known = PHIClassifier.PHI_FIELDS | PHIClassifier.NON_PHI_FIELDS
unknown_field_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),
    min_size=1,
    max_size=40,
).filter(lambda s: s not in _all_known)


# ---------------------------------------------------------------------------
# Property 8a: Known PHI fields are classified as PHI
# ---------------------------------------------------------------------------

@given(field=phi_field_strategy)
@h_settings(max_examples=100)
def test_known_phi_fields_classified_as_phi(field: str):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 8: PHI classification correctness
    **Validates: Requirements 6.1, 6.2**

    For any known PHI field, is_phi() must return True.
    """
    assert classifier.is_phi(field) is True


# ---------------------------------------------------------------------------
# Property 8b: Known non-PHI fields are classified as non-PHI
# ---------------------------------------------------------------------------

@given(field=non_phi_field_strategy)
@h_settings(max_examples=100)
def test_known_non_phi_fields_classified_as_non_phi(field: str):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 8: PHI classification correctness
    **Validates: Requirements 6.4**

    For any known non-PHI field, is_phi() must return False.
    """
    assert classifier.is_phi(field) is False


# ---------------------------------------------------------------------------
# Property 8c: Unknown fields default to PHI (safe default)
# ---------------------------------------------------------------------------

@given(field=unknown_field_strategy)
@h_settings(max_examples=100)
def test_unknown_fields_default_to_phi(field: str):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 8: PHI classification correctness
    **Validates: Requirements 6.5**

    For any field name not in the explicit classification map,
    is_phi() must return True (safe default).
    """
    assert classifier.is_phi(field) is True


# ---------------------------------------------------------------------------
# Property 8d: classify_document covers all keys and is consistent
# ---------------------------------------------------------------------------

@given(
    data=st.dictionaries(
        keys=st.one_of(phi_field_strategy, non_phi_field_strategy, unknown_field_strategy),
        values=st.text(min_size=0, max_size=20),
        min_size=1,
        max_size=10,
    )
)
@h_settings(max_examples=100)
def test_classify_document_covers_all_keys(data: dict):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 8: PHI classification correctness
    **Validates: Requirements 6.1, 6.2, 6.5**

    classify_document must return a mapping for every key in the input,
    and each value must match is_phi for that key.
    """
    result = classifier.classify_document(data)
    assert set(result.keys()) == set(data.keys())
    for k, v in result.items():
        assert v == classifier.is_phi(k)


# ---------------------------------------------------------------------------
# Property 8e: extract_phi + extract_non_phi partition the input
# ---------------------------------------------------------------------------

@given(
    data=st.dictionaries(
        keys=st.one_of(phi_field_strategy, non_phi_field_strategy, unknown_field_strategy),
        values=st.text(min_size=0, max_size=20),
        min_size=0,
        max_size=10,
    )
)
@h_settings(max_examples=100)
def test_extract_phi_and_non_phi_partition(data: dict):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 8: PHI classification correctness
    **Validates: Requirements 6.1, 6.2, 6.5**

    extract_phi_fields and extract_non_phi_fields must form a complete,
    non-overlapping partition of the input data.
    """
    phi = classifier.extract_phi_fields(data)
    non_phi = classifier.extract_non_phi_fields(data)

    # No overlap
    assert set(phi.keys()).isdisjoint(set(non_phi.keys()))
    # Complete coverage
    assert set(phi.keys()) | set(non_phi.keys()) == set(data.keys())
    # Values preserved
    for k, v in phi.items():
        assert data[k] == v
    for k, v in non_phi.items():
        assert data[k] == v
