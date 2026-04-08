"""
Tests de propriété pour le pipeline d'agents — Diagno-Pilot

# Feature: llm-llamaindex-hipaa-refactor

Property 15: Agent PHI boundary enforcement
Property 16: Agent result aggregation preserves confidence scores

**Validates: Requirements 10.2, 10.3, 10.6**
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.consultation import DifferentialDiagnosis
from backend.models.patient import PatientProfile
from backend.services.agent_pipeline import (
    AgentPipeline,
    AgentResult,
)
from backend.services.llm_router import LLMRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run an async coroutine in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Realistic symptom dicts
_symptom_st = st.fixed_dictionaries({
    "name": st.sampled_from([
        "fièvre", "céphalées", "toux", "diarrhée", "vomissements",
        "douleur abdominale", "fatigue", "éruption cutanée",
    ]),
    "severity": st.sampled_from(["mild", "moderate", "severe"]),
    "duration_days": st.integers(min_value=1, max_value=30),
})

_symptoms_st = st.lists(_symptom_st, min_size=1, max_size=5)

_region_st = st.sampled_from(["TG", "BJ", "ALL", None])

# Confidence scores between 0 and 1
_confidence_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Agent names
_agent_names_st = st.sampled_from(list(AgentPipeline.AGENTS.keys()))

# Differential diagnosis
_diagnosis_st = st.builds(
    DifferentialDiagnosis,
    condition=st.text(min_size=1, max_size=50).filter(str.strip),
    probability=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    icd_code=st.one_of(st.none(), st.from_regex(r"[A-Z]\d{2}\.\d", fullmatch=True)),
    matching_symptoms=st.lists(st.text(min_size=1, max_size=20), max_size=3),
)

# Agent result with configurable endpoint
_agent_result_st = st.builds(
    AgentResult,
    agent_name=_agent_names_st,
    sub_question=st.text(min_size=1, max_size=100),
    chunks=st.just([{"document_id": "d1", "title": "t", "source": "s", "excerpt": "e", "page": 1}]),
    confidence_score=_confidence_st,
    partial_differential=st.lists(_diagnosis_st, min_size=0, max_size=3),
    endpoint_used=st.sampled_from([LLMRouter.PRIMARY_MODEL, LLMRouter.FALLBACK_MODEL]),
    duration_seconds=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    error=st.just(None),
)


# ---------------------------------------------------------------------------
# Property 15: Agent PHI boundary enforcement
# ---------------------------------------------------------------------------

@given(
    symptoms=_symptoms_st,
    region=_region_st,
    endpoint=st.sampled_from([LLMRouter.PRIMARY_MODEL, LLMRouter.FALLBACK_MODEL]),
)
@h_settings(max_examples=100)
def test_phi_boundary_enforcement(
    symptoms: list[dict],
    region: str | None,
    endpoint: str,
):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 15: Agent PHI boundary enforcement
    **Validates: Requirements 10.2, 10.3**

    For any agent execution:
    - If the endpoint is the local Model_Container, full PHI context SHALL
      be present in the request.
    - If the endpoint is the external GPT-5 fallback, the request context
      SHALL contain zero PHI (BAA stripping applied by LLMRouter).

    We verify this by mocking the pipeline and checking that:
    1. The pipeline.query() receives the patient_profile (PHI) regardless
       of endpoint — the LLMRouter handles stripping internally.
    2. When fallback is used, LLMRouter.last_used reports the fallback model.
    """
    from backend.models.document import DocumentSource, RAGResponse

    # Build a patient profile with PHI
    patient = PatientProfile(
        full_name="Test Patient",
        weight_kg=70.0,
        allergies=["penicillin"],
        current_medications=["amoxicillin"],
    )

    # Mock pipeline that records what context it received
    captured_contexts: list[Any] = []

    async def mock_query(question, context=None, region=None, source_filter=None, **kw):
        captured_contexts.append(context)
        return RAGResponse(
            answer="diagnostic : Paludisme",
            sources=[DocumentSource(document_id="d1", title="t", source="s")],
            llm_used=endpoint,
            confidence_score=0.7,
            fallback_used=(endpoint == LLMRouter.FALLBACK_MODEL),
        )

    mock_pipeline = MagicMock()
    mock_pipeline.query = AsyncMock(side_effect=mock_query)

    mock_router = MagicMock(spec=LLMRouter)
    mock_router.last_used = endpoint
    mock_router.PRIMARY_MODEL = LLMRouter.PRIMARY_MODEL
    mock_router.FALLBACK_MODEL = LLMRouter.FALLBACK_MODEL

    agent_pipeline = AgentPipeline(
        pipeline=mock_pipeline,
        llm_router=mock_router,
        audit_logger=None,
    )

    result = run(agent_pipeline.run(symptoms, patient_profile=patient, region=region))

    # The pipeline always receives the full patient profile — PHI boundary
    # enforcement happens inside LLMRouter.generate(), not in AgentPipeline.
    # AgentPipeline passes full context; LLMRouter strips PHI on fallback.
    for ctx in captured_contexts:
        assert ctx is patient, (
            "AgentPipeline must pass full patient profile to pipeline.query(); "
            "PHI stripping is handled by LLMRouter on fallback path."
        )

    # Verify endpoint reporting
    for agent_result in result.agent_results:
        if agent_result.error is None:
            assert agent_result.endpoint_used == endpoint


# ---------------------------------------------------------------------------
# Property 15b: Fallback path reports fallback_used=True
# ---------------------------------------------------------------------------

@given(symptoms=_symptoms_st, region=_region_st)
@h_settings(max_examples=100)
def test_fallback_path_reports_fallback_used(
    symptoms: list[dict],
    region: str | None,
):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 15: Agent PHI boundary enforcement
    **Validates: Requirements 10.2, 10.3**

    When all agents are served by the GPT-5 fallback, the aggregated
    DiagnosticResponse SHALL have fallback_used=True.
    """
    from backend.models.document import DocumentSource, RAGResponse

    async def mock_query(question, context=None, region=None, source_filter=None, **kw):
        return RAGResponse(
            answer="diagnostic : Fièvre typhoïde",
            sources=[DocumentSource(document_id="d1", title="t", source="s")],
            llm_used=LLMRouter.FALLBACK_MODEL,
            confidence_score=0.5,
            fallback_used=True,
        )

    mock_pipeline = MagicMock()
    mock_pipeline.query = AsyncMock(side_effect=mock_query)

    mock_router = MagicMock(spec=LLMRouter)
    mock_router.last_used = LLMRouter.FALLBACK_MODEL
    mock_router.PRIMARY_MODEL = LLMRouter.PRIMARY_MODEL
    mock_router.FALLBACK_MODEL = LLMRouter.FALLBACK_MODEL

    agent_pipeline = AgentPipeline(
        pipeline=mock_pipeline,
        llm_router=mock_router,
        audit_logger=None,
    )

    result = run(agent_pipeline.run(symptoms, region=region))
    assert result.fallback_used is True


# ---------------------------------------------------------------------------
# Property 16: Agent result aggregation preserves confidence scores
# ---------------------------------------------------------------------------

@given(
    agent_results=st.lists(_agent_result_st, min_size=1, max_size=5),
)
@h_settings(max_examples=100)
def test_aggregation_preserves_confidence_scores(
    agent_results: list[AgentResult],
):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 16: Agent result aggregation
    **Validates: Requirements 10.6**

    For any set of agent results with confidence scores, the aggregation
    function SHALL produce a combined result whose confidence score is the
    arithmetic mean of the individual agent confidence scores.
    """
    mock_pipeline = MagicMock()
    mock_router = MagicMock(spec=LLMRouter)
    mock_router.PRIMARY_MODEL = LLMRouter.PRIMARY_MODEL
    mock_router.FALLBACK_MODEL = LLMRouter.FALLBACK_MODEL

    pipeline = AgentPipeline(
        pipeline=mock_pipeline,
        llm_router=mock_router,
        audit_logger=None,
    )

    response = pipeline._aggregate(agent_results)

    # All non-error results contribute to the mean
    non_error = [r for r in agent_results if r.error is None]
    if non_error:
        expected_mean = sum(r.confidence_score for r in non_error) / len(non_error)
        assert abs(response.confidence_score - expected_mean) < 1e-9, (
            f"Expected confidence {expected_mean}, got {response.confidence_score}"
        )
    else:
        assert response.confidence_score == 0.0


# ---------------------------------------------------------------------------
# Property 16b: All partial differentials included in aggregated output
# ---------------------------------------------------------------------------

@given(
    agent_results=st.lists(_agent_result_st, min_size=1, max_size=5),
)
@h_settings(max_examples=100)
def test_aggregation_includes_all_partial_differentials(
    agent_results: list[AgentResult],
):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 16: Agent result aggregation
    **Validates: Requirements 10.6**

    All agent partial differentials SHALL be included in the aggregated
    output (deduplicated by condition name, keeping highest probability).
    """
    mock_pipeline = MagicMock()
    mock_router = MagicMock(spec=LLMRouter)
    mock_router.PRIMARY_MODEL = LLMRouter.PRIMARY_MODEL
    mock_router.FALLBACK_MODEL = LLMRouter.FALLBACK_MODEL

    pipeline = AgentPipeline(
        pipeline=mock_pipeline,
        llm_router=mock_router,
        audit_logger=None,
    )

    response = pipeline._aggregate(agent_results)

    # Collect all unique conditions from active agents (with chunks, no error)
    active = [r for r in agent_results if r.error is None and r.chunks]
    expected_conditions: dict[str, float] = {}
    for r in active:
        for diag in r.partial_differential:
            key = diag.condition.strip().lower()
            if key not in expected_conditions or diag.probability > expected_conditions[key]:
                expected_conditions[key] = diag.probability

    actual_conditions = {
        d.condition.strip().lower(): d.probability for d in response.diagnoses
    }

    # Every expected condition must be present
    for cond, prob in expected_conditions.items():
        assert cond in actual_conditions, (
            f"Condition '{cond}' missing from aggregated output"
        )
        assert abs(actual_conditions[cond] - prob) < 1e-9, (
            f"Condition '{cond}': expected prob {prob}, got {actual_conditions[cond]}"
        )
