"""Unit tests for DiagnosticOrchestrator."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock


from backend.models.consultation import DifferentialDiagnosis, Symptom
from backend.models.document import RAGResponse
from backend.models.patient import PatientProfile
from backend.services.diagnostic_parser import DiagnosticParser
from backend.services.diagnostic_service import DiagnosticOrchestrator, DiagnosticService
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

    mock_prompt_builder.build.assert_called_once_with(symptoms, profile)


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

    assert result is expected


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
