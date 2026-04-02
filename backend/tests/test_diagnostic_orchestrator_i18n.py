"""
Property-based tests for DiagnosticOrchestrator i18n behaviour.

Feature: i18n-medical-content, Property 10: DiagnosticResult always carries locale metadata
Validates: Requirements 4.4, 4.7
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.consultation import Symptom
from backend.models.document import RAGResponse
from backend.services.diagnostic_service import DiagnosticOrchestrator, DiagnosticResult
from backend.services.prompt_builder import PromptBuilder

SUPPORTED_LOCALES = ["fr-TG", "fr-BJ", "en"]

_VALID_DIAGNOSES_JSON = json.dumps([
    {"condition": "Malaria", "probability": 0.75, "icd_code": "B54"},
    {"condition": "Typhoid", "probability": 0.55, "icd_code": "A01.0"},
    {"condition": "Dengue", "probability": 0.35, "icd_code": "A90"},
])


def _make_orchestrator(answer: str = _VALID_DIAGNOSES_JSON) -> DiagnosticOrchestrator:
    mock_rag = AsyncMock()
    mock_rag.query = AsyncMock(
        return_value=RAGResponse(
            answer=answer,
            sources=[],
            fallback_used=False,
            degraded_warning=None,
            llm_used="primary",
        )
    )
    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_prompt_builder.build.return_value = "built prompt"
    return DiagnosticOrchestrator(rag_service=mock_rag, prompt_builder=mock_prompt_builder)


# ---------------------------------------------------------------------------
# Property 10: DiagnosticResult always carries locale metadata
# Feature: i18n-medical-content, Property 10: DiagnosticResult always carries locale metadata
# ---------------------------------------------------------------------------

@given(locale=st.sampled_from(SUPPORTED_LOCALES))
@settings(max_examples=100)
def test_property_10_diagnostic_result_carries_locale_metadata(locale: str):
    """Property 10: DiagnosticResult.locale equals the requested locale for all supported locales."""
    import asyncio
    orchestrator = _make_orchestrator()
    symptoms = [Symptom(name="fever", severity="moderate", duration_days=3)]
    result: DiagnosticResult = asyncio.run(
        orchestrator.get_differential_diagnosis(symptoms=symptoms, locale=locale)
    )
    assert result.locale == locale, (
        f"Expected DiagnosticResult.locale={locale!r} but got {result.locale!r}"
    )
    assert isinstance(result.language_mismatch, bool)


@given(locale=st.sampled_from(SUPPORTED_LOCALES))
@settings(max_examples=100)
def test_property_10_locale_fallback_when_metadata_absent(locale: str):
    """Property 10 (fallback): locale field is set to requested locale even when LLM answer has no locale metadata."""
    import asyncio
    # LLM answer is plain text with no locale metadata — simulates Req 4.7
    orchestrator = _make_orchestrator(answer=_VALID_DIAGNOSES_JSON)
    symptoms = [Symptom(name="cough", severity="mild", duration_days=2)]
    result: DiagnosticResult = asyncio.run(
        orchestrator.get_differential_diagnosis(symptoms=symptoms, locale=locale)
    )
    assert result.locale == locale


# ---------------------------------------------------------------------------
# Unit tests: language mismatch detection (Req 4.5)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_language_mismatch_detected_when_llm_responds_in_wrong_language():
    """Mock LLM returning English response for fr-TG request → language_mismatch: True."""
    # English text that langdetect reliably identifies as English
    english_answer = json.dumps([
        {"condition": "Malaria", "probability": 0.75, "icd_code": "B54"},
        {"condition": "Typhoid fever", "probability": 0.55, "icd_code": "A01.0"},
        {"condition": "Dengue fever", "probability": 0.35, "icd_code": "A90"},
    ])
    orchestrator = _make_orchestrator(answer=english_answer)
    symptoms = [Symptom(name="fever", severity="moderate", duration_days=3)]

    # Request fr-TG but LLM responds in English
    # We patch langdetect.detect to return "en" deterministically
    import unittest.mock as mock
    with mock.patch("backend.services.diagnostic_service.langdetect") as mock_ld:
        mock_ld.detect.return_value = "en"
        result = await orchestrator.get_differential_diagnosis(
            symptoms=symptoms,
            locale="fr-TG",
        )

    assert result.language_mismatch is True
    assert result.locale == "fr-TG"


@pytest.mark.asyncio
async def test_no_language_mismatch_when_llm_responds_in_correct_language():
    """Mock LLM returning French response for fr-TG request → language_mismatch: False."""
    french_answer = json.dumps([
        {"condition": "Paludisme", "probability": 0.75, "icd_code": "B54"},
        {"condition": "Fièvre typhoïde", "probability": 0.55, "icd_code": "A01.0"},
        {"condition": "Dengue", "probability": 0.35, "icd_code": "A90"},
    ])
    orchestrator = _make_orchestrator(answer=french_answer)
    symptoms = [Symptom(name="fièvre", severity="modérée", duration_days=3)]

    import unittest.mock as mock
    with mock.patch("backend.services.diagnostic_service.langdetect") as mock_ld:
        mock_ld.detect.return_value = "fr"
        result = await orchestrator.get_differential_diagnosis(
            symptoms=symptoms,
            locale="fr-TG",
        )

    assert result.language_mismatch is False
    assert result.locale == "fr-TG"


@pytest.mark.asyncio
async def test_language_mismatch_false_for_en_locale_with_english_response():
    """English locale + English LLM response → language_mismatch: False."""
    english_answer = json.dumps([
        {"condition": "Malaria", "probability": 0.75, "icd_code": "B54"},
        {"condition": "Typhoid", "probability": 0.55, "icd_code": "A01.0"},
        {"condition": "Dengue", "probability": 0.35, "icd_code": "A90"},
    ])
    orchestrator = _make_orchestrator(answer=english_answer)
    symptoms = [Symptom(name="fever", severity="moderate", duration_days=3)]

    import unittest.mock as mock
    with mock.patch("backend.services.diagnostic_service.langdetect") as mock_ld:
        mock_ld.detect.return_value = "en"
        result = await orchestrator.get_differential_diagnosis(
            symptoms=symptoms,
            locale="en",
        )

    assert result.language_mismatch is False
    assert result.locale == "en"


@pytest.mark.asyncio
async def test_language_mismatch_non_fatal_when_langdetect_raises():
    """If langdetect raises, language_mismatch stays False and no exception propagates."""
    orchestrator = _make_orchestrator()
    symptoms = [Symptom(name="fever", severity="moderate", duration_days=3)]

    import unittest.mock as mock
    with mock.patch("backend.services.diagnostic_service.langdetect") as mock_ld:
        mock_ld.detect.side_effect = Exception("langdetect failure")
        result = await orchestrator.get_differential_diagnosis(
            symptoms=symptoms,
            locale="fr-TG",
        )

    assert result.language_mismatch is False
    assert result.locale == "fr-TG"
