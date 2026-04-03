"""
Property-based tests for Synthesis_Agent — Diagno-Pilot Improvements
"""
from __future__ import annotations

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from backend.agents.synthesis_agent import Synthesis_Agent
from backend.models.consultation import DifferentialDiagnosis
from backend.services.mcp_host import AgentResult


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_st_condition = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")))

_st_differential_diagnosis = st.builds(
    DifferentialDiagnosis,
    condition=_st_condition,
    probability=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    icd_code=st.none(),
    matching_symptoms=st.just([]),
)

_st_agent_result_with_chunks = st.builds(
    AgentResult,
    agent_name=st.text(min_size=1, max_size=30),
    sub_question=st.text(min_size=1, max_size=100),
    chunks=st.lists(st.just({"content": "chunk"}), min_size=1, max_size=5),
    confidence_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    partial_differential=st.lists(_st_differential_diagnosis, min_size=0, max_size=5),
    timed_out=st.just(False),
    omitted=st.just(False),
)

_st_agent_result_no_chunks = st.builds(
    AgentResult,
    agent_name=st.text(min_size=1, max_size=30),
    sub_question=st.text(min_size=1, max_size=100),
    chunks=st.just([]),
    confidence_score=st.just(0.0),
    partial_differential=st.lists(_st_differential_diagnosis, min_size=0, max_size=5),
    timed_out=st.just(False),
    omitted=st.just(False),
)

_st_any_agent_result = st.one_of(_st_agent_result_with_chunks, _st_agent_result_no_chunks)


# ---------------------------------------------------------------------------
# Feature: diagno-pilot-improvements, Property 6: Synthesis_Agent garantit au moins 3 diagnostics différentiels
# ---------------------------------------------------------------------------

# **Validates: Requirements 2.7**
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(agent_results=st.lists(_st_any_agent_result, min_size=0, max_size=4))
def test_property_6_synthesis_agent_guarantees_at_least_3_diagnoses(
    agent_results: list[AgentResult],
) -> None:
    """Validates: Requirements 2.7

    For any set of agent results (including the case where all agents return
    zero chunks), Synthesis_Agent.synthesize() must produce a list of diagnoses
    of length >= 3, adding 'confidence: low' placeholder entries if necessary.
    """
    agent = Synthesis_Agent()
    result = agent.synthesize(agent_results)

    assert len(result.diagnoses) >= 3, (
        f"Expected at least 3 diagnoses, got {len(result.diagnoses)} "
        f"with {len(agent_results)} agent(s)"
    )


# ---------------------------------------------------------------------------
# Feature: diagno-pilot-improvements, Property 7: Agents sans chunks exclus de la synthèse
# ---------------------------------------------------------------------------

# **Validates: Requirements 2.9**
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    agents_with_chunks=st.lists(
        _st_agent_result_with_chunks,
        min_size=0,
        max_size=3,
    ),
    agents_without_chunks=st.lists(
        _st_agent_result_no_chunks,
        min_size=1,
        max_size=3,
    ),
)
def test_property_7_agents_without_chunks_excluded_from_synthesis(
    agents_with_chunks: list[AgentResult],
    agents_without_chunks: list[AgentResult],
) -> None:
    """Validates: Requirements 2.9

    For any set of agent results where some agents return zero chunks,
    Synthesis_Agent.synthesize() must:
    1. Exclude those agents from the merged result (their partial_differential
       should not appear in the final diagnoses unless also present in active agents).
    2. Record their omission in the DiagnosticResult's degraded_warning.
    """
    # Ensure agent names are unique across both lists to avoid ambiguity
    for i, agent in enumerate(agents_without_chunks):
        agent.agent_name = f"omitted_agent_{i}"
    for i, agent in enumerate(agents_with_chunks):
        agent.agent_name = f"active_agent_{i}"

    # Give omitted agents unique diagnoses not present in active agents
    omitted_conditions = set()
    for i, agent in enumerate(agents_without_chunks):
        unique_condition = f"__omitted_condition_{i}__"
        agent.partial_differential = [
            DifferentialDiagnosis(condition=unique_condition, probability=0.9)
        ]
        omitted_conditions.add(unique_condition.strip().lower())

    all_results = agents_with_chunks + agents_without_chunks
    agent = Synthesis_Agent()
    result = agent.synthesize(all_results)

    # 1. Omitted agents' unique conditions must NOT appear in final diagnoses
    final_conditions = {d.condition.strip().lower() for d in result.diagnoses}
    for omitted_cond in omitted_conditions:
        assert omitted_cond not in final_conditions, (
            f"Condition from omitted agent '{omitted_cond}' should not appear in diagnoses"
        )

    # 2. degraded_warning must be set and contain the omitted agent names
    assert result.degraded_warning is not None, (
        "degraded_warning must be set when agents with no chunks are omitted"
    )
    for agent_result in agents_without_chunks:
        assert agent_result.agent_name in result.degraded_warning, (
            f"Omitted agent '{agent_result.agent_name}' must appear in degraded_warning"
        )
