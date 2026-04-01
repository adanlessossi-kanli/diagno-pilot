"""
Property test for DiagnosticOrchestrator — Diagno-Pilot

Property 8: DiagnosticOrchestrator always returns at least 3 diagnoses
**Validates: Requirements 3.1, 3.6, 4.3**

For any list of symptoms and any patient profile (including None),
DiagnosticOrchestrator.get_differential_diagnosis() must return a list of at
least 3 DifferentialDiagnosis objects with the correct structure (non-empty
condition, probability in [0.0, 1.0]).
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.consultation import DifferentialDiagnosis, Symptom
from backend.models.document import RAGResponse
from backend.models.patient import PatientProfile
from backend.services.diagnostic_service import DiagnosticOrchestrator

# ---------------------------------------------------------------------------
# Strategies — reuse patterns from test_diagnostic_property.py
# ---------------------------------------------------------------------------

severity_strategy = st.sampled_from(["mild", "moderate", "severe"])

symptom_strategy = st.builds(
    Symptom,
    name=st.text(min_size=1, max_size=50).filter(str.strip),
    severity=st.one_of(st.none(), severity_strategy),
    duration_days=st.one_of(st.none(), st.integers(min_value=1, max_value=365)),
)

symptoms_strategy = st.lists(symptom_strategy, min_size=1, max_size=10)

patient_profile_strategy = st.one_of(
    st.none(),
    st.builds(
        PatientProfile,
        full_name=st.text(min_size=1, max_size=50).filter(str.strip),
        date_of_birth=st.none(),
        weight_kg=st.one_of(st.none(), st.floats(min_value=1.0, max_value=200.0, allow_nan=False)),
        age_group=st.none(),
        allergies=st.lists(st.text(min_size=1, max_size=20), max_size=3),
        current_medications=st.lists(st.text(min_size=1, max_size=20), max_size=3),
    ),
)


def _make_rag_answer() -> str:
    """Return a JSON array with exactly 3 valid diagnoses."""
    diagnoses = [
        {"condition": "Malaria", "probability": 0.75, "icd_code": "B54"},
        {"condition": "Typhoid fever", "probability": 0.55, "icd_code": "A01.0"},
        {"condition": "Dengue fever", "probability": 0.35, "icd_code": "A90"},
    ]
    return json.dumps(diagnoses)


# ---------------------------------------------------------------------------
# Property 8: DiagnosticOrchestrator always returns at least 3 diagnoses
# ---------------------------------------------------------------------------

@given(symptoms=symptoms_strategy, patient_profile=patient_profile_strategy)
@h_settings(max_examples=100)
def test_p8_orchestrator_always_returns_at_least_3_diagnoses(
    symptoms: list[Symptom],
    patient_profile: PatientProfile | None,
):
    """
    Feature: code-quality, Property 8:
    For any list of symptoms and any patient profile (including None),
    DiagnosticOrchestrator.get_differential_diagnosis() must return a list of
    at least 3 DifferentialDiagnosis objects with the correct structure.

    **Validates: Requirements 3.1, 3.6, 4.3**
    """
    mock_rag = AsyncMock()
    mock_rag.query = AsyncMock(
        return_value=RAGResponse(
            answer=_make_rag_answer(),
            sources=[],
            llm_used="mock",
        )
    )

    orchestrator = DiagnosticOrchestrator(rag_service=mock_rag)

    result: list[DifferentialDiagnosis] = asyncio.run(
        orchestrator.get_differential_diagnosis(symptoms, patient_profile)
    )

    assert len(result) >= 3, (
        f"Expected at least 3 diagnoses, got {len(result)}"
    )

    for diag in result:
        assert 0.0 <= diag.probability <= 1.0, (
            f"Probability {diag.probability!r} out of range for condition {diag.condition!r}"
        )
        assert diag.condition and diag.condition.strip(), (
            f"Condition field must be non-empty, got {diag.condition!r}"
        )
