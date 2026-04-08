# Feature: diagno-pilot-improvements, Property 10: Invariants structurels des diagnostics LLM
"""
Tests de propriete pour DiagnosticParser -- Diagno-Pilot

Property 10 : Invariants structurels des diagnostics LLM
**Validates: Requirements 6.1, 6.3, 6.4**

Note: _validate_diagnoses() was extracted from DiagnosticService into DiagnosticParser
as part of the code-quality refactoring (Task 3). These tests now exercise
DiagnosticParser directly, which is the canonical location for validation logic.

Pour toute reponse LLM parsee avec succes par DiagnosticParser.parse(),
la liste resultante doit satisfaire simultanement :
  (a) len(diagnoses) >= 3
  (b) chaque condition est une chaine non vide
  (c) chaque probability in [0.0, 1.0]
  (d) chaque icd_code present correspond au regex ^[A-Z][0-9]{2}(\\.[0-9]{1,4})?$
"""
from __future__ import annotations

import json
import re as _re

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.consultation import DifferentialDiagnosis
from backend.services.diagnostic_parser import DiagnosticParser
from backend.services.diagnostic_service import DiagnosticService

# ---------------------------------------------------------------------------
# Strategies -- valid inputs
# ---------------------------------------------------------------------------

valid_condition_st = st.text(min_size=1).filter(lambda s: s.strip() != "")

valid_probability_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

valid_icd_code_st = st.one_of(
    st.none(),
    st.from_regex(r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$", fullmatch=True),
)

valid_diagnosis_st = st.builds(
    DifferentialDiagnosis,
    condition=valid_condition_st,
    probability=valid_probability_st,
    icd_code=valid_icd_code_st,
)

valid_diagnoses_list_st = st.lists(valid_diagnosis_st, min_size=3, max_size=10)


def _make_json_answer(diagnoses: list[DifferentialDiagnosis]) -> str:
    return json.dumps([
        {"condition": d.condition, "probability": d.probability, "icd_code": d.icd_code}
        for d in diagnoses
    ])


# ---------------------------------------------------------------------------
# Property 10 -- valid lists must NOT raise
# ---------------------------------------------------------------------------

@given(diagnoses=valid_diagnoses_list_st)
@h_settings(max_examples=100)
def test_p10_valid_diagnoses_do_not_raise(diagnoses: list[DifferentialDiagnosis]):
    """
    Feature: diagno-pilot-improvements, Property 10:
    Pour toute liste valide de DifferentialDiagnosis (3-10 items, condition non vide,
    probability in [0.0, 1.0], icd_code conforme ou absent), DiagnosticParser.parse()
    ne doit pas lever d'exception et retourner au moins 3 diagnostics valides.

    **Validates: Requirements 6.1, 6.3, 6.4**
    """
    parser = DiagnosticParser()
    result, parse_failed = parser.parse(_make_json_answer(diagnoses))
    assert len(result) >= 3
    for d in result:
        assert d.condition and d.condition.strip()
        assert 0.0 <= d.probability <= 1.0


# ---------------------------------------------------------------------------
# Property 10 -- empty list returns 3 placeholders
# ---------------------------------------------------------------------------

def test_p10_empty_list_returns_placeholders():
    """
    Feature: diagno-pilot-improvements, Property 10 (a):
    Une liste vide retourne 3 placeholders.

    **Validates: Requirements 6.1**
    """
    parser = DiagnosticParser()
    result, parse_failed = parser.parse("[]")
    assert len(result) == 3
    assert parse_failed is True
    for d in result:
        assert d.probability == 0.0
        assert d.icd_code is None


# ---------------------------------------------------------------------------
# Property 10 -- DiagnosticService alias still works
# ---------------------------------------------------------------------------

def test_diagnostic_service_alias():
    """DiagnosticService is an alias for DiagnosticOrchestrator."""
    from backend.services.diagnostic_service import DiagnosticOrchestrator
    assert DiagnosticService is DiagnosticOrchestrator


# ---------------------------------------------------------------------------
# Property 10 -- probabilities always clamped to [0.0, 1.0]
# ---------------------------------------------------------------------------

def test_p10_out_of_range_probability_is_clamped():
    """
    Feature: diagno-pilot-improvements, Property 10 (c):
    DiagnosticParser clamps out-of-range probabilities to [0.0, 1.0].

    **Validates: Requirements 6.3**
    """
    entries = [
        {"condition": "A", "probability": 1.5, "icd_code": None},
        {"condition": "B", "probability": -0.5, "icd_code": None},
        {"condition": "C", "probability": 0.5, "icd_code": None},
    ]
    parser = DiagnosticParser()
    result, _parse_failed = parser.parse(json.dumps(entries))
    for d in result:
        assert 0.0 <= d.probability <= 1.0


# ---------------------------------------------------------------------------
# Property 10 -- invalid icd_code is nullified
# ---------------------------------------------------------------------------

def test_p10_invalid_icd_code_is_nullified():
    """
    Feature: diagno-pilot-improvements, Property 10 (d):
    DiagnosticParser nullifies icd_code values that do not match ICD-10 format.

    **Validates: Requirements 6.4**
    """
    entries = [
        {"condition": "A", "probability": 0.8, "icd_code": "not-valid"},
        {"condition": "B", "probability": 0.5, "icd_code": "B54"},
        {"condition": "C", "probability": 0.3, "icd_code": "123"},
    ]
    parser = DiagnosticParser()
    result, _parse_failed = parser.parse(json.dumps(entries))
    for d in result:
        if d.icd_code is not None:
            assert _re.match(r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$", d.icd_code)
