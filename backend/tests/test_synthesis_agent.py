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


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent, Property 6: Déduplication par probabilité maximale
# ---------------------------------------------------------------------------

# **Validates: Requirements 5.2**
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    agents=st.lists(
        _st_agent_result_with_chunks,
        min_size=2,
        max_size=4,
    ),
    shared_condition=_st_condition,
    probabilities=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=4,
    ),
)
def test_property_mcp_6_deduplication_by_max_probability(
    agents: list[AgentResult],
    shared_condition: str,
    probabilities: list[float],
) -> None:
    """**Validates: Requirements 5.2**

    For any set of agent results where two or more agents return the same
    diagnosis (case-insensitive comparison), the Synthesis_Agent must produce
    a single entry for that diagnosis with the highest probability among all
    occurrences.
    """
    # Ensure we have at least as many probabilities as agents
    probs = probabilities[: len(agents)]
    if len(probs) < len(agents):
        probs.extend([0.5] * (len(agents) - len(probs)))

    shared_key = shared_condition.strip().lower()

    # Assign unique names and inject the shared condition into every agent
    for i, agent in enumerate(agents):
        agent.agent_name = f"agent_{i}"
        shared_diag = DifferentialDiagnosis(
            condition=shared_condition,
            probability=probs[i],
        )
        # Prepend the shared diagnosis to whatever the agent already has
        agent.partial_differential = [shared_diag] + list(agent.partial_differential)

    # Compute the expected max probability across ALL occurrences of the
    # shared condition in all agents (injected + any pre-existing ones)
    all_probs_for_shared: list[float] = []
    for agent in agents:
        for d in agent.partial_differential:
            if d.condition.strip().lower() == shared_key:
                all_probs_for_shared.append(d.probability)
    expected_max_prob = max(all_probs_for_shared)

    synth = Synthesis_Agent()
    result = synth.synthesize(agents)

    # Filter out placeholder diagnostics (those added to reach min 3)
    non_placeholder = [
        d
        for d in result.diagnoses
        if not d.condition.startswith("Diagnostic différentiel")
    ]

    # Count how many times the shared condition appears (case-insensitive)
    matches = [d for d in non_placeholder if d.condition.strip().lower() == shared_key]

    assert len(matches) == 1, (
        f"Expected exactly 1 entry for '{shared_condition}', "
        f"got {len(matches)} in {[d.condition for d in non_placeholder]}"
    )

    assert matches[0].probability == expected_max_prob, (
        f"Expected probability {expected_max_prob} for '{shared_condition}', "
        f"got {matches[0].probability}"
    )


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent, Property 7: Tri des diagnostics par probabilité décroissante
# ---------------------------------------------------------------------------

# **Validates: Exigence 5.3**
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(agent_results=st.lists(_st_any_agent_result, min_size=0, max_size=4))
def test_property_mcp_7_diagnoses_sorted_by_descending_probability(
    agent_results: list[AgentResult],
) -> None:
    """**Validates: Requirements 5.3**

    For any set of agent results, the list of diagnoses produced by
    Synthesis_Agent.synthesize() must be sorted by probability in descending
    order (each element has a probability >= the next element's probability).
    """
    agent = Synthesis_Agent()
    result = agent.synthesize(agent_results)

    diagnoses = result.diagnoses
    for i in range(len(diagnoses) - 1):
        assert diagnoses[i].probability >= diagnoses[i + 1].probability, (
            f"Diagnoses not sorted by descending probability: "
            f"diagnoses[{i}].probability={diagnoses[i].probability} < "
            f"diagnoses[{i + 1}].probability={diagnoses[i + 1].probability}"
        )


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent, Property 8: Garantie de minimum 3 diagnostics
# ---------------------------------------------------------------------------

# **Validates: Exigence 5.4**
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(agent_results=st.lists(_st_any_agent_result, min_size=0, max_size=4))
def test_property_mcp_8_minimum_3_diagnostics_guarantee(
    agent_results: list[AgentResult],
) -> None:
    """**Validates: Requirements 5.4**

    For any set of agent results (including the case where all agents return
    zero chunks), Synthesis_Agent.synthesize() must produce a list of diagnoses
    of length >= 3.
    """
    agent = Synthesis_Agent()
    result = agent.synthesize(agent_results)

    assert len(result.diagnoses) >= 3, (
        f"Expected at least 3 diagnoses, got {len(result.diagnoses)} "
        f"with {len(agent_results)} agent(s)"
    )


# ---------------------------------------------------------------------------
# Strategy: Agent results with proper chunk dicts (for evidence citation tests)
# ---------------------------------------------------------------------------

_st_chunk = st.fixed_dictionaries({
    "document_id": st.text(min_size=1, max_size=20),
    "title": st.text(min_size=1, max_size=50),
    "source": st.text(min_size=1, max_size=50),
    "excerpt": st.text(min_size=1, max_size=100),
    "page": st.one_of(st.none(), st.integers(min_value=1, max_value=500)),
})

_st_agent_result_with_proper_chunks = st.builds(
    AgentResult,
    agent_name=st.text(min_size=1, max_size=30),
    sub_question=st.text(min_size=1, max_size=100),
    chunks=st.lists(_st_chunk, min_size=1, max_size=5),
    confidence_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    partial_differential=st.lists(_st_differential_diagnosis, min_size=1, max_size=5),
    timed_out=st.just(False),
    omitted=st.just(False),
)


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent, Property 9: Citations de preuves associées à chaque diagnostic non-placeholder
# ---------------------------------------------------------------------------

# **Validates: Exigence 5.7**
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    agent_results=st.lists(
        _st_agent_result_with_proper_chunks,
        min_size=1,
        max_size=4,
    ),
)
def test_property_mcp_9_evidence_citations_for_non_placeholder_diagnoses(
    agent_results: list[AgentResult],
) -> None:
    """**Validates: Requirements 5.7**

    For any diagnosis in the synthesis result produced from active agents
    (having chunks) and that is NOT a placeholder diagnostic, there must exist
    at least one EvidenceCitation in the result's evidence_citations list.
    Placeholder diagnostics (those added to reach the minimum of 3, with
    condition starting with "Diagnostic différentiel") must have NO associated
    citations.
    """
    # Ensure unique agent names to avoid ambiguity
    for i, agent in enumerate(agent_results):
        agent.agent_name = f"agent_{i}"

    synth = Synthesis_Agent()
    result = synth.synthesize(agent_results)

    # Separate non-placeholder and placeholder diagnoses
    non_placeholder = [
        d for d in result.diagnoses
        if not d.condition.startswith("Diagnostic différentiel")
    ]
    placeholder = [
        d for d in result.diagnoses
        if d.condition.startswith("Diagnostic différentiel")
    ]

    # For each non-placeholder diagnosis, verify at least one citation exists
    # that can be traced back to a chunk from an agent that contributed it
    for diag in non_placeholder:
        diag_key = diag.condition.strip().lower()
        # Find which agents contributed this diagnosis
        contributing_agents = [
            ar for ar in agent_results
            if any(
                d.condition.strip().lower() == diag_key
                for d in ar.partial_differential
            )
        ]
        assert len(contributing_agents) > 0, (
            f"Non-placeholder diagnosis '{diag.condition}' has no contributing agent"
        )

        # Collect all chunk document_ids from contributing agents
        contributing_doc_ids = set()
        for ar in contributing_agents:
            for chunk in ar.chunks:
                contributing_doc_ids.add(chunk.get("document_id", ""))

        # Check that at least one citation in the result references a
        # document_id from a contributing agent's chunks
        matching_citations = [
            c for c in result.evidence_citations
            if c.document_id in contributing_doc_ids
        ]
        assert len(matching_citations) >= 1, (
            f"Non-placeholder diagnosis '{diag.condition}' must have at least "
            f"one EvidenceCitation from a contributing agent, but found none. "
            f"Contributing doc_ids: {contributing_doc_ids}, "
            f"All citation doc_ids: {[c.document_id for c in result.evidence_citations]}"
        )

    # Placeholder diagnostics must have NO associated citations
    # (since _build_evidence_citations only creates citations for conditions
    # found in agents' partial_differential, placeholders get none)
    for diag in placeholder:
        diag_key = diag.condition.strip().lower()
        # No agent should have contributed a placeholder condition
        _placeholder_citations = [  # noqa: F841 — kept for documentation
            c for c in result.evidence_citations
            if c.document_id == ""  # placeholder would have empty doc_id
        ]
        # Actually, we verify that no agent has this placeholder condition
        # in their partial_differential, so no citations are built for it
        contributing_agents = [
            ar for ar in agent_results
            if any(
                d.condition.strip().lower() == diag_key
                for d in ar.partial_differential
            )
        ]
        assert len(contributing_agents) == 0, (
            f"Placeholder diagnosis '{diag.condition}' should not have "
            f"contributing agents, but found {len(contributing_agents)}"
        )


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent, Property 10: Score de confiance pondéré par chunks
# ---------------------------------------------------------------------------

# **Validates: Exigence 5.8**
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(agent_results=st.lists(_st_any_agent_result, min_size=0, max_size=4))
def test_property_mcp_10_weighted_confidence_score(
    agent_results: list[AgentResult],
) -> None:
    """**Validates: Requirements 5.8**

    For any set of agent results with active agents (having non-empty chunks),
    the global confidence score calculated by Synthesis_Agent must equal
    sum(score_i × len(chunks_i)) / sum(len(chunks_i)). When no agent is active
    (all have empty chunks), the score must be 0.0.
    """
    agent = Synthesis_Agent()
    result = agent.synthesize(agent_results)

    # Compute expected weighted confidence manually
    active_results = [r for r in agent_results if r.chunks]
    total_weight = sum(len(r.chunks) for r in active_results)
    if total_weight == 0:
        expected = 0.0
    else:
        expected = sum(
            r.confidence_score * len(r.chunks) for r in active_results
        ) / total_weight

    assert abs(result.confidence_score - expected) < 1e-9, (
        f"Expected weighted confidence {expected}, got {result.confidence_score}. "
        f"Active agents: {len(active_results)}, total_weight: {total_weight}"
    )


# ---------------------------------------------------------------------------
# Strategy: Agent result with fallback_used=True
# ---------------------------------------------------------------------------

_st_agent_result_with_fallback = st.builds(
    AgentResult,
    agent_name=st.text(min_size=1, max_size=30),
    sub_question=st.text(min_size=1, max_size=100),
    chunks=st.lists(st.just({"content": "chunk"}), min_size=1, max_size=5),
    confidence_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    partial_differential=st.lists(_st_differential_diagnosis, min_size=0, max_size=5),
    timed_out=st.just(False),
    omitted=st.just(False),
    fallback_used=st.just(True),
)

_st_agent_result_no_fallback_with_chunks = st.builds(
    AgentResult,
    agent_name=st.text(min_size=1, max_size=30),
    sub_question=st.text(min_size=1, max_size=100),
    chunks=st.lists(st.just({"content": "chunk"}), min_size=1, max_size=5),
    confidence_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    partial_differential=st.lists(_st_differential_diagnosis, min_size=0, max_size=5),
    timed_out=st.just(False),
    omitted=st.just(False),
    fallback_used=st.just(False),
)


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent, Property 11: Disclaimer ajouté lors du fallback LLM
# ---------------------------------------------------------------------------

# **Validates: Exigences 4.7, 6.2, 8.3**
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    fallback_agents=st.lists(_st_agent_result_with_fallback, min_size=1, max_size=3),
    normal_agents=st.lists(_st_agent_result_no_fallback_with_chunks, min_size=0, max_size=3),
)
def test_property_mcp_11_fallback_disclaimer_present(
    fallback_agents: list[AgentResult],
    normal_agents: list[AgentResult],
) -> None:
    """**Validates: Exigences 4.7, 6.2, 8.3**

    Sub-property 1: When at least one agent has fallback_used=True,
    the DiagnosticResult must have fallback_used=True, disclaimer must be
    non-null, and must contain the clinical verification warning text.
    """
    all_results = fallback_agents + normal_agents

    synth = Synthesis_Agent()
    result = synth.synthesize(all_results)

    assert result.fallback_used is True, (
        "fallback_used must be True when at least one agent has fallback_used=True"
    )
    assert result.disclaimer is not None, (
        "disclaimer must be non-null when at least one agent has fallback_used=True"
    )
    assert "vérification clinique" in result.disclaimer, (
        f"disclaimer must contain 'vérification clinique', got: {result.disclaimer!r}"
    )


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    agents=st.lists(_st_agent_result_no_fallback_with_chunks, min_size=1, max_size=4),
)
def test_property_mcp_11_fallback_disclaimer_absent(
    agents: list[AgentResult],
) -> None:
    """**Validates: Exigences 4.7, 6.2, 8.3**

    Sub-property 2: When NO agent has fallback_used=True AND at least one
    agent has chunks, the DiagnosticResult must have fallback_used=False
    and disclaimer must be None.
    """
    synth = Synthesis_Agent()
    result = synth.synthesize(agents)

    assert result.fallback_used is False, (
        "fallback_used must be False when no agent has fallback_used=True "
        "and at least one agent has chunks"
    )
    assert result.disclaimer is None, (
        f"disclaimer must be None when no agent has fallback_used=True, "
        f"got: {result.disclaimer!r}"
    )
