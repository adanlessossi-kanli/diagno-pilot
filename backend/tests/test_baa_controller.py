"""
Tests de propriété pour le contrôleur BAA — Diagno-Pilot

# Feature: llm-llamaindex-hipaa-refactor, Property 11: BAA PHI stripping with placeholder substitution

**Validates: Requirements 5.4, 9.1, 9.2**

Propriété 11 : Pour tout contexte LLM contenant des champs PHI de
PatientProfile, l'opération strip_phi du BAA_Controller remplace toutes
les valeurs PHI par les placeholders correspondants, et le contexte
résultant ne contient aucune valeur PHI.
"""
from __future__ import annotations

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.baa_controller import BAAController
from backend.services.phi_classifier import PHIClassifier

classifier = PHIClassifier()
controller = BAAController()

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Realistic PHI values
_phi_value_st = st.text(min_size=1, max_size=100).filter(
    lambda s: s not in set(BAAController.PHI_PLACEHOLDERS.values())
    and s.strip() != ""
)

# Build a context message containing a mix of PHI and non-PHI fields
_phi_field_entry = st.sampled_from(sorted(BAAController.PHI_PLACEHOLDERS.keys()))

_context_msg_with_phi = st.fixed_dictionaries(
    {"content": st.text(min_size=1, max_size=200), "role": st.just("user")},
    optional={
        field: _phi_value_st for field in sorted(BAAController.PHI_PLACEHOLDERS.keys())
    },
)

_context_strategy = st.lists(_context_msg_with_phi, min_size=1, max_size=5)


# ---------------------------------------------------------------------------
# Property 11a: All PHI values replaced with placeholders after strip_phi
# ---------------------------------------------------------------------------

@given(context=_context_strategy)
@h_settings(max_examples=100)
def test_strip_phi_replaces_all_phi_with_placeholders(context: list[dict]):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 11: BAA PHI stripping
    **Validates: Requirements 9.1, 9.2**

    For any context containing PHI fields, strip_phi SHALL replace all PHI
    values with their corresponding placeholders.
    """
    stripped = controller.strip_phi(context, classifier)

    assert len(stripped) == len(context)

    for orig_msg, stripped_msg in zip(context, stripped):
        for field, placeholder in BAAController.PHI_PLACEHOLDERS.items():
            if field in orig_msg:
                assert stripped_msg[field] == placeholder, (
                    f"Field '{field}' should be '{placeholder}', "
                    f"got '{stripped_msg[field]}'"
                )
        # Non-PHI fields preserved
        assert stripped_msg.get("content") == orig_msg.get("content")
        assert stripped_msg.get("role") == orig_msg.get("role")


# ---------------------------------------------------------------------------
# Property 11b: Stripped context contains zero PHI values
# ---------------------------------------------------------------------------

@given(context=_context_strategy)
@h_settings(max_examples=100)
def test_stripped_context_contains_zero_phi(context: list[dict]):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 11: BAA PHI stripping
    **Validates: Requirements 5.4, 9.1**

    After strip_phi, verify_no_phi SHALL not raise — the context is clean.
    """
    stripped = controller.strip_phi(context, classifier)

    # verify_no_phi should not raise
    controller.verify_no_phi(stripped, classifier)


# ---------------------------------------------------------------------------
# Property 11c: Original PHI values do not appear in stripped context
# ---------------------------------------------------------------------------

@given(context=_context_strategy)
@h_settings(max_examples=100)
def test_original_phi_values_absent_from_stripped_context(context: list[dict]):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 11: BAA PHI stripping
    **Validates: Requirements 9.1, 9.2**

    For any context, no original PHI value from the input appears in the
    stripped output (except if the original value happened to be a placeholder).
    """
    # Collect original PHI values
    original_phi_values: set[str] = set()
    placeholder_values = set(BAAController.PHI_PLACEHOLDERS.values())
    for msg in context:
        for field in BAAController.PHI_PLACEHOLDERS:
            if field in msg:
                val = msg[field]
                if isinstance(val, str) and val not in placeholder_values:
                    original_phi_values.add(val)

    stripped = controller.strip_phi(context, classifier)

    # Collect string values from PHI fields in stripped context
    stripped_phi_values: set[str] = set()
    for msg in stripped:
        for field in BAAController.PHI_PLACEHOLDERS:
            if field in msg and isinstance(msg[field], str):
                stripped_phi_values.add(msg[field])

    # No original PHI value should remain in PHI fields of stripped output
    leaked = original_phi_values & stripped_phi_values
    assert not leaked, f"PHI values leaked into stripped context: {leaked}"


# ---------------------------------------------------------------------------
# Property 11d: strip_phi is idempotent
# ---------------------------------------------------------------------------

@given(context=_context_strategy)
@h_settings(max_examples=50)
def test_strip_phi_is_idempotent(context: list[dict]):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 11: BAA PHI stripping
    **Validates: Requirements 9.1**

    Applying strip_phi twice produces the same result as applying it once.
    """
    once = controller.strip_phi(context, classifier)
    twice = controller.strip_phi(once, classifier)

    assert once == twice
