# Feature: diagno-pilot-improvements, Property 10: Invariants structurels des diagnostics LLM
"""
Tests de propriété pour DiagnosticService._validate_diagnoses() — Diagno-Pilot

Property 10 : Invariants structurels des diagnostics LLM
**Validates: Requirements 6.1, 6.3, 6.4**

Pour toute réponse LLM parsée avec succès par DiagnosticService._validate_diagnoses(),
la liste résultante doit satisfaire simultanément :
  (a) 1 ≤ len(diagnoses) ≤ 10
  (b) chaque condition est une chaîne non vide
  (c) chaque probability ∈ [0.0, 1.0]
  (d) chaque icd_code présent correspond au regex ^[A-Z][0-9]{2}(\\.[0-9]{1,4})?$
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.consultation import DifferentialDiagnosis
from backend.services.diagnostic_service import DiagnosticService

# ---------------------------------------------------------------------------
# Strategies — valid inputs
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

valid_diagnoses_list_st = st.lists(valid_diagnosis_st, min_size=1, max_size=10)

# ---------------------------------------------------------------------------
# Strategies — invalid inputs
# Note: DifferentialDiagnosis has Pydantic Field(ge=0, le=1) on probability,
# so we use model_construct() to bypass validation when building invalid objects.
# ---------------------------------------------------------------------------

invalid_probability_st = st.one_of(
    st.floats(max_value=-0.001, allow_nan=False),
    st.floats(min_value=1.001, allow_nan=False),
)


@st.composite
def invalid_probability_diagnosis_st(draw) -> DifferentialDiagnosis:
    """Build a DifferentialDiagnosis with an out-of-range probability (bypassing Pydantic)."""
    condition = draw(valid_condition_st)
    probability = draw(invalid_probability_st)
    icd_code = draw(valid_icd_code_st)
    return DifferentialDiagnosis.model_construct(
        condition=condition,
        probability=probability,
        icd_code=icd_code,
        matching_symptoms=[],
    )


@st.composite
def invalid_condition_diagnosis_st(draw) -> DifferentialDiagnosis:
    """Build a DifferentialDiagnosis with an empty condition (bypassing Pydantic)."""
    probability = draw(valid_probability_st)
    icd_code = draw(valid_icd_code_st)
    return DifferentialDiagnosis.model_construct(
        condition="",
        probability=probability,
        icd_code=icd_code,
        matching_symptoms=[],
    )


# A diagnosis with a malformed icd_code (non-None, non-matching)
import re as _re  # noqa: E402

invalid_icd_code_st = st.text(min_size=1).filter(
    lambda s: s.strip() != "" and not _re.match(
        r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$", s
    )
)


@st.composite
def invalid_icd_diagnosis_st(draw) -> DifferentialDiagnosis:
    """Build a DifferentialDiagnosis with a malformed icd_code."""
    condition = draw(valid_condition_st)
    probability = draw(valid_probability_st)
    icd_code = draw(invalid_icd_code_st)
    return DifferentialDiagnosis.model_construct(
        condition=condition,
        probability=probability,
        icd_code=icd_code,
        matching_symptoms=[],
    )


def _make_service() -> DiagnosticService:
    """Return a DiagnosticService with a dummy RAG service (not used in _validate_diagnoses)."""
    from unittest.mock import MagicMock
    return DiagnosticService(rag_service=MagicMock())


# ---------------------------------------------------------------------------
# Property 10 — valid lists must NOT raise
# ---------------------------------------------------------------------------

@given(diagnoses=valid_diagnoses_list_st)
@h_settings(max_examples=100)
def test_p10_valid_diagnoses_do_not_raise(diagnoses: list[DifferentialDiagnosis]):
    """
    Feature: diagno-pilot-improvements, Property 10:
    Pour toute liste valide de DifferentialDiagnosis (1–10 items, condition non vide,
    probability ∈ [0.0, 1.0], icd_code conforme ou absent), _validate_diagnoses()
    ne doit pas lever d'exception.

    **Validates: Requirements 6.1, 6.3, 6.4**
    """
    service = _make_service()
    # Must not raise
    service._validate_diagnoses(diagnoses, raw_response="<generated>")


# ---------------------------------------------------------------------------
# Property 10 — empty list must raise HTTPException(502)
# ---------------------------------------------------------------------------

def test_p10_empty_list_raises_502():
    """
    Feature: diagno-pilot-improvements, Property 10 (a):
    Une liste vide doit lever HTTPException(502).

    **Validates: Requirements 6.1**
    """
    service = _make_service()
    with pytest.raises(HTTPException) as exc_info:
        service._validate_diagnoses([], raw_response="[]")
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "llm_response_invalid"


# ---------------------------------------------------------------------------
# Property 10 — list with more than 10 items must raise HTTPException(502)
# ---------------------------------------------------------------------------

@given(
    diagnoses=st.lists(valid_diagnosis_st, min_size=11, max_size=20)
)
@h_settings(max_examples=100)
def test_p10_too_many_diagnoses_raises_502(diagnoses: list[DifferentialDiagnosis]):
    """
    Feature: diagno-pilot-improvements, Property 10 (a):
    Une liste de plus de 10 diagnostics doit lever HTTPException(502).

    **Validates: Requirements 6.1**
    """
    service = _make_service()
    with pytest.raises(HTTPException) as exc_info:
        service._validate_diagnoses(diagnoses, raw_response="<generated>")
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "llm_response_invalid"


# ---------------------------------------------------------------------------
# Property 10 — empty condition must raise HTTPException(502)
# ---------------------------------------------------------------------------

@given(
    valid_prefix=st.lists(valid_diagnosis_st, min_size=0, max_size=5),
    invalid_diag=invalid_condition_diagnosis_st(),
    valid_suffix=st.lists(valid_diagnosis_st, min_size=0, max_size=4),
)
@h_settings(max_examples=100)
def test_p10_empty_condition_raises_502(
    valid_prefix: list[DifferentialDiagnosis],
    invalid_diag: DifferentialDiagnosis,
    valid_suffix: list[DifferentialDiagnosis],
):
    """
    Feature: diagno-pilot-improvements, Property 10 (b):
    Une liste contenant un diagnostic avec une condition vide doit lever HTTPException(502).

    **Validates: Requirements 6.3**
    """
    diagnoses = valid_prefix + [invalid_diag] + valid_suffix
    # Clamp to 1–10 to isolate the condition check (not the length check)
    diagnoses = diagnoses[:10] if len(diagnoses) > 10 else diagnoses
    if not diagnoses:
        diagnoses = [invalid_diag]

    service = _make_service()
    with pytest.raises(HTTPException) as exc_info:
        service._validate_diagnoses(diagnoses, raw_response="<generated>")
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "llm_response_invalid"


# ---------------------------------------------------------------------------
# Property 10 — out-of-range probability must raise HTTPException(502)
# ---------------------------------------------------------------------------

@given(
    valid_prefix=st.lists(valid_diagnosis_st, min_size=0, max_size=5),
    invalid_diag=invalid_probability_diagnosis_st(),
    valid_suffix=st.lists(valid_diagnosis_st, min_size=0, max_size=4),
)
@h_settings(max_examples=100)
def test_p10_invalid_probability_raises_502(
    valid_prefix: list[DifferentialDiagnosis],
    invalid_diag: DifferentialDiagnosis,
    valid_suffix: list[DifferentialDiagnosis],
):
    """
    Feature: diagno-pilot-improvements, Property 10 (c):
    Une liste contenant un diagnostic avec probability hors de [0.0, 1.0]
    doit lever HTTPException(502).

    **Validates: Requirements 6.3**
    """
    diagnoses = valid_prefix + [invalid_diag] + valid_suffix
    diagnoses = diagnoses[:10] if len(diagnoses) > 10 else diagnoses
    if not diagnoses:
        diagnoses = [invalid_diag]

    service = _make_service()
    with pytest.raises(HTTPException) as exc_info:
        service._validate_diagnoses(diagnoses, raw_response="<generated>")
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "llm_response_invalid"


# ---------------------------------------------------------------------------
# Property 10 — malformed icd_code must raise HTTPException(502)
# ---------------------------------------------------------------------------

@given(
    valid_prefix=st.lists(valid_diagnosis_st, min_size=0, max_size=5),
    invalid_diag=invalid_icd_diagnosis_st(),
    valid_suffix=st.lists(valid_diagnosis_st, min_size=0, max_size=4),
)
@h_settings(max_examples=100)
def test_p10_invalid_icd_code_raises_502(
    valid_prefix: list[DifferentialDiagnosis],
    invalid_diag: DifferentialDiagnosis,
    valid_suffix: list[DifferentialDiagnosis],
):
    """
    Feature: diagno-pilot-improvements, Property 10 (d):
    Une liste contenant un diagnostic avec un icd_code non conforme au regex
    ^[A-Z][0-9]{2}(\\.[0-9]{1,4})?$ doit lever HTTPException(502).

    **Validates: Requirements 6.4**
    """
    diagnoses = valid_prefix + [invalid_diag] + valid_suffix
    diagnoses = diagnoses[:10] if len(diagnoses) > 10 else diagnoses
    if not diagnoses:
        diagnoses = [invalid_diag]

    service = _make_service()
    with pytest.raises(HTTPException) as exc_info:
        service._validate_diagnoses(diagnoses, raw_response="<generated>")
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "llm_response_invalid"
