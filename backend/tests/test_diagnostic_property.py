"""
Tests de propriété pour DiagnosticService — Diagno-Pilot

**Validates: Requirements REQ-02**

Propriété 5 : Pour tout ensemble valide de symptômes, le service retourne
au moins 3 diagnostics différentiels avec un score de probabilité entre 0 et 1.
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
from backend.services.diagnostic_service import DiagnosticService

# ---------------------------------------------------------------------------
# Strategies
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
# Property 5 : at least 3 diagnoses with probability in [0, 1]
# ---------------------------------------------------------------------------

@given(symptoms=symptoms_strategy, patient_profile=patient_profile_strategy)
@h_settings(max_examples=100)
def test_differential_diagnosis_returns_at_least_3_with_valid_probabilities(
    symptoms: list[Symptom],
    patient_profile: PatientProfile | None,
):
    """
    **Validates: Requirements REQ-02**

    For any valid set of symptoms, DiagnosticService.get_differential_diagnosis
    must return at least 3 diagnoses, each with:
      - a probability score in [0.0, 1.0]
      - a non-empty condition field
    """
    mock_rag = AsyncMock()
    mock_rag.query = AsyncMock(
        return_value=RAGResponse(
            answer=_make_rag_answer(),
            sources=[],
            llm_used="mock",
        )
    )

    service = DiagnosticService(rag_service=mock_rag)

    result: list[DifferentialDiagnosis] = asyncio.run(
        service.get_differential_diagnosis(symptoms, patient_profile)
    )

    # At least 3 diagnoses returned
    assert len(result) >= 3, (
        f"Expected at least 3 diagnoses, got {len(result)}"
    )

    for diag in result:
        # Probability must be in [0.0, 1.0]
        assert 0.0 <= diag.probability <= 1.0, (
            f"Probability {diag.probability!r} out of range for condition {diag.condition!r}"
        )
        # Condition must be non-empty
        assert diag.condition and diag.condition.strip(), (
            f"Condition field must be non-empty, got {diag.condition!r}"
        )
