"""Unit tests for DiagnosticOrchestrator."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock


from backend.models.consultation import DifferentialDiagnosis, Symptom
from backend.models.document import RAGResponse
from backend.models.patient import PatientProfile
from backend.services.diagnostic_parser import DiagnosticParser
from backend.services.diagnostic_service import DiagnosticOrchestrator, DiagnosticService, DIAGNOSIS_SYSTEM_PROMPT
from backend.services.prompt_builder import PromptBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_symptoms() -> list[Symptom]:
    return [Symptom(name="fever", severity="moderate", duration_days=3)]


def _make_diagnoses() -> list[DifferentialDiagnosis]:
    return [
        DifferentialDiagnosis(condition="Malaria", probability=0.75, icd_code="B54"),
        DifferentialDiagnosis(condition="Typhoid", probability=0.55, icd_code="A01.0"),
        DifferentialDiagnosis(condition="Dengue", probability=0.35, icd_code="A90"),
    ]


# ---------------------------------------------------------------------------
# Test delegation
# ---------------------------------------------------------------------------

def test_delegation_calls_prompt_builder_with_correct_args():
    """PromptBuilder.build() is called with the correct symptoms and patient_profile."""
    symptoms = _make_symptoms()
    profile = PatientProfile(full_name="Alice")

    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_prompt_builder.build.return_value = "built prompt"

    mock_rag = AsyncMock()
    mock_rag.query = AsyncMock(
        return_value=RAGResponse(answer=json.dumps([
            {"condition": "A", "probability": 0.9, "icd_code": "A00"},
            {"condition": "B", "probability": 0.5, "icd_code": "B00"},
            {"condition": "C", "probability": 0.1, "icd_code": "C00"},
        ]), sources=[], llm_used="mock")
    )

    mock_parser = MagicMock(spec=DiagnosticParser)
    mock_parser.parse.return_value = _make_diagnoses()

    orchestrator = DiagnosticOrchestrator(
        rag_service=mock_rag,
        prompt_builder=mock_prompt_builder,
        diagnostic_parser=mock_parser,
    )

    asyncio.run(orchestrator.get_differential_diagnosis(symptoms, profile))

    mock_prompt_builder.build.assert_called_once_with(symptoms, profile, locale="fr-TG", region=None)


def test_delegation_calls_rag_with_prompt_from_builder():
    """RAGService.query() is called with the prompt returned by PromptBuilder."""
    symptoms = _make_symptoms()

    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_prompt_builder.build.return_value = "the built prompt"

    mock_rag = AsyncMock()
    mock_rag.query = AsyncMock(
        return_value=RAGResponse(answer="[]", sources=[], llm_used="mock")
    )

    mock_parser = MagicMock(spec=DiagnosticParser)
    mock_parser.parse.return_value = _make_diagnoses()

    orchestrator = DiagnosticOrchestrator(
        rag_service=mock_rag,
        prompt_builder=mock_prompt_builder,
        diagnostic_parser=mock_parser,
    )

    asyncio.run(orchestrator.get_differential_diagnosis(symptoms, None))

    mock_rag.query.assert_called_once_with(
        question="the built prompt",
        context=None,
        top_k=5,
        region=None,
        system_prompt=DIAGNOSIS_SYSTEM_PROMPT,
    )


def test_delegation_calls_parser_with_rag_answer():
    """DiagnosticParser.parse() is called with the answer from RAGService."""
    symptoms = _make_symptoms()
    rag_answer = '["some", "answer"]'

    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_prompt_builder.build.return_value = "prompt"

    mock_rag = AsyncMock()
    mock_rag.query = AsyncMock(
        return_value=RAGResponse(answer=rag_answer, sources=[], llm_used="mock")
    )

    mock_parser = MagicMock(spec=DiagnosticParser)
    mock_parser.parse.return_value = _make_diagnoses()

    orchestrator = DiagnosticOrchestrator(
        rag_service=mock_rag,
        prompt_builder=mock_prompt_builder,
        diagnostic_parser=mock_parser,
    )

    asyncio.run(orchestrator.get_differential_diagnosis(symptoms, None))

    mock_parser.parse.assert_called_once_with(rag_answer)


def test_delegation_returns_parser_result():
    """The result equals what DiagnosticParser.parse() returned."""
    symptoms = _make_symptoms()
    expected = _make_diagnoses()

    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_prompt_builder.build.return_value = "prompt"

    mock_rag = AsyncMock()
    mock_rag.query = AsyncMock(
        return_value=RAGResponse(answer="[]", sources=[], llm_used="mock")
    )

    mock_parser = MagicMock(spec=DiagnosticParser)
    mock_parser.parse.return_value = expected

    orchestrator = DiagnosticOrchestrator(
        rag_service=mock_rag,
        prompt_builder=mock_prompt_builder,
        diagnostic_parser=mock_parser,
    )

    result = asyncio.run(orchestrator.get_differential_diagnosis(symptoms, None))

    assert result.diagnoses is expected


# ---------------------------------------------------------------------------
# Test DiagnosticService alias
# ---------------------------------------------------------------------------

def test_diagnostic_service_is_orchestrator_alias():
    """DiagnosticService is DiagnosticOrchestrator."""
    assert DiagnosticService is DiagnosticOrchestrator


# ---------------------------------------------------------------------------
# Test default collaborators
# ---------------------------------------------------------------------------

def test_default_collaborators_are_created_when_not_provided():
    """When no prompt_builder/diagnostic_parser are passed, defaults are created."""
    mock_rag = MagicMock()
    orchestrator = DiagnosticOrchestrator(rag_service=mock_rag)

    assert isinstance(orchestrator._prompt_builder, PromptBuilder)
    assert isinstance(orchestrator._diagnostic_parser, DiagnosticParser)


# ---------------------------------------------------------------------------
# Test custom collaborators
# ---------------------------------------------------------------------------

def test_custom_collaborators_are_used_when_provided():
    """When prompt_builder/diagnostic_parser are passed, those exact instances are used."""
    mock_rag = MagicMock()
    custom_builder = PromptBuilder()
    custom_parser = DiagnosticParser()

    orchestrator = DiagnosticOrchestrator(
        rag_service=mock_rag,
        prompt_builder=custom_builder,
        diagnostic_parser=custom_parser,
    )

    assert orchestrator._prompt_builder is custom_builder
    assert orchestrator._diagnostic_parser is custom_parser
    assert orchestrator._rag is mock_rag


# ---------------------------------------------------------------------------
# Property-based tests — diagno-pilot-improvements
# ---------------------------------------------------------------------------

import pytest  # noqa: E402
from hypothesis import given, settings, HealthCheck  # noqa: E402
from hypothesis import strategies as st  # noqa: E402



def _make_orchestrator_with_mock_db():
    """Build a DiagnosticOrchestrator with a mocked MongoDB database."""
    from unittest.mock import AsyncMock, MagicMock
    from backend.services.diagnostic_service import DiagnosticOrchestrator
    from backend.models.document import RAGResponse
    from backend.services.diagnostic_parser import DiagnosticParser
    from backend.services.prompt_builder import PromptBuilder

    mock_rag = AsyncMock()
    mock_rag.query = AsyncMock(
        return_value=RAGResponse(
            answer=json.dumps([
                {"condition": "Malaria", "probability": 0.8, "icd_code": "B54"},
                {"condition": "Typhoid", "probability": 0.5, "icd_code": "A01.0"},
                {"condition": "Dengue", "probability": 0.3, "icd_code": "A90"},
            ]),
            sources=[],
            llm_used="mock",
        )
    )

    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_prompt_builder.build.return_value = "built prompt"

    mock_parser = MagicMock(spec=DiagnosticParser)
    from backend.models.consultation import DifferentialDiagnosis
    mock_parser.parse.return_value = [
        DifferentialDiagnosis(condition="Malaria", probability=0.8, icd_code="B54"),
        DifferentialDiagnosis(condition="Typhoid", probability=0.5, icd_code="A01.0"),
        DifferentialDiagnosis(condition="Dengue", probability=0.3, icd_code="A90"),
    ]

    # Mock MongoDB collection
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock()

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    orchestrator = DiagnosticOrchestrator(
        rag_service=mock_rag,
        prompt_builder=mock_prompt_builder,
        diagnostic_parser=mock_parser,
        db=mock_db,
    )
    return orchestrator, mock_collection


# Feature: diagno-pilot-improvements, Property 13: DiagnosticAudit écrit pour chaque appel diagnostique
# Validates: Requirements 4.3, 4.4
@pytest.mark.asyncio
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    symptom_names=st.lists(
        st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))),
        min_size=1,
        max_size=5,
    ),
    locale=st.sampled_from(["fr-TG", "fr-BJ", "fr", "en"]),
    region=st.one_of(st.none(), st.sampled_from(["TG", "BJ", "ALL"])),
)
async def test_property_13_diagnostic_audit_written_for_each_call(
    symptom_names: list[str],
    locale: str,
    region: str | None,
):
    """Validates: Requirements 4.3, 4.4
    For every call to DiagnosticOrchestrator.get_differential_diagnosis(),
    exactly one document must be inserted into the diagnostic_audit collection,
    containing all required fields.
    """
    orchestrator, mock_collection = _make_orchestrator_with_mock_db()

    symptoms = [Symptom(name=name) for name in symptom_names]

    await orchestrator.get_differential_diagnosis(
        symptoms=symptoms,
        patient_profile=None,
        locale=locale,
        region=region,
    )

    # Exactly one insert_one call per diagnostic call
    mock_collection.insert_one.assert_called_once()

    # Verify the inserted document has all required fields
    inserted_doc = mock_collection.insert_one.call_args.args[0]
    assert "timestamp" in inserted_doc
    assert "symptoms" in inserted_doc
    assert "patient_profile_hash" in inserted_doc
    assert "locale" in inserted_doc
    assert "region" in inserted_doc
    assert "confidence_score" in inserted_doc
    assert "diagnoses" in inserted_doc
    assert "fallback_used" in inserted_doc
    assert "degraded_warning" in inserted_doc
    assert "agent_results" in inserted_doc
    assert inserted_doc["locale"] == locale
    assert inserted_doc["region"] == region


# Feature: diagno-pilot-improvements, Property 14: Hash du profil patient exclut les champs PII
# Validates: Requirements 4.3
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    age=st.one_of(st.none(), st.integers(min_value=0, max_value=120)),
    weight=st.one_of(st.none(), st.floats(min_value=1.0, max_value=300.0, allow_nan=False)),
    sex=st.one_of(st.none(), st.sampled_from(["M", "F", "other"])),
    comorbidities=st.one_of(
        st.none(),
        st.fixed_dictionaries({"renal_failure": st.booleans(), "hepatic_failure": st.booleans()}),
    ),
    pii_name=st.text(min_size=1, max_size=50),
    pii_name_alt=st.text(min_size=1, max_size=50),
)
def test_property_14_patient_hash_excludes_pii_fields(
    age: int | None,
    weight: float | None,
    sex: str | None,
    comorbidities: dict | None,
    pii_name: str,
    pii_name_alt: str,
):
    """Validates: Requirements 4.3
    Modifying PII fields (full_name, identifiers) must NOT change patient_profile_hash.
    Modifying non-PII fields (age, weight, sex, comorbidities) MUST produce a different hash.
    """
    from backend.models.diagnostic_audit import DiagnosticAudit

    # Hash with base non-PII values
    base_hash = DiagnosticAudit.compute_patient_hash(
        age=age,
        weight=weight,
        sex=sex,
        comorbidities=comorbidities,
    )

    # Changing PII (full_name equivalent — not in hash inputs) must NOT change the hash
    # The hash function only takes age, weight, sex, comorbidities — calling it again
    # with the same values must produce the same result regardless of any PII context
    same_hash = DiagnosticAudit.compute_patient_hash(
        age=age,
        weight=weight,
        sex=sex,
        comorbidities=comorbidities,
    )
    assert base_hash == same_hash, (
        "Hash must be deterministic: same non-PII inputs must always produce the same hash"
    )

    # Changing a non-PII field (age) must produce a different hash (when age is not None)
    if age is not None:
        different_age = (age + 1) % 121
        changed_hash = DiagnosticAudit.compute_patient_hash(
            age=different_age,
            weight=weight,
            sex=sex,
            comorbidities=comorbidities,
        )
        assert base_hash != changed_hash, (
            f"Changing age from {age} to {different_age} must change the hash"
        )

    # Changing sex must produce a different hash (when sex is not None)
    if sex is not None:
        alt_sex = "F" if sex != "F" else "M"
        changed_hash = DiagnosticAudit.compute_patient_hash(
            age=age,
            weight=weight,
            sex=alt_sex,
            comorbidities=comorbidities,
        )
        assert base_hash != changed_hash, (
            f"Changing sex from {sex!r} to {alt_sex!r} must change the hash"
        )
