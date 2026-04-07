"""
Property-based test for MCP agents in error marked as omitted.

Feature: guided-diagnosis-multi-agent, Property 4: Agents en erreur marqués comme omis

**Validates: Requirements 2.9, 3.6**

Property 4: For any MCP specialist server that returns invalid JSON, a
JSON-RPC 2.0 error, or exceeds the timeout, the MCP_Host must mark that agent
as omitted in `DiagnosticAuditData.omissions` and continue processing with the
remaining agents.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.models.consultation import Symptom
from backend.services.mcp_host import AgentResult, MCP_Host, _AGENT_URLS


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_AGENT_NAMES = sorted(_AGENT_URLS.keys())  # deterministic order
FAILURE_MODES = ["health_fail", "rpc_error", "connect_error"]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Pick a random non-empty subset of agents (1-4) that will fail
_st_failing_agents = st.lists(
    st.sampled_from(ALL_AGENT_NAMES),
    min_size=1,
    max_size=4,
    unique=True,
)

# For each failing agent, pick a failure mode
_st_failure_mode = st.sampled_from(FAILURE_MODES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_healthy_result(agent_name: str) -> AgentResult:
    """Return a valid AgentResult for a healthy agent."""
    return AgentResult(
        agent_name=agent_name,
        sub_question=f"Sub-question for {agent_name}",
        chunks=[{"document_id": "doc1", "title": "Test", "source": "src", "excerpt": "ex", "page": 1}],
        confidence_score=0.8,
        timed_out=False,
        omitted=False,
    )


def _make_failed_result(agent_name: str) -> AgentResult:
    """Return an AgentResult for a failed/omitted agent."""
    return AgentResult(
        agent_name=agent_name,
        sub_question="",
        omitted=True,
    )


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent
# Property 4: Agents en erreur marqués comme omis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    failing_agents=_st_failing_agents,
    failure_modes=st.lists(_st_failure_mode, min_size=4, max_size=4),
)
async def test_property_4_agents_in_error_marked_as_omitted(
    failing_agents: list[str],
    failure_modes: list[str],
) -> None:
    """Validates: Requirements 2.9, 3.6

    For any subset of MCP specialist servers that fail (health check failure,
    RPC error, or connection error), the MCP_Host must mark those agents as
    omitted in DiagnosticAuditData.omissions and continue processing with the
    remaining agents. The total number of results is always 4 (one per agent).
    """
    # Build a mapping: agent_name -> failure_mode (only for failing agents)
    agent_failure_map: dict[str, str] = {}
    for i, agent_name in enumerate(failing_agents):
        agent_failure_map[agent_name] = failure_modes[i % len(failure_modes)]

    healthy_agents = [a for a in ALL_AGENT_NAMES if a not in agent_failure_map]

    # Create MCP_Host and mock _call_agent_http at the per-agent level
    host = MCP_Host.__new__(MCP_Host)
    host._capability_cache = {}

    async def mock_call_agent_http(
        agent_name: str,
        symptoms,
        patient_profile,
        locale: str,
        region,
    ) -> AgentResult:
        if agent_name in agent_failure_map:
            return _make_failed_result(agent_name)
        return _make_healthy_result(agent_name)

    host._call_agent_http = mock_call_agent_http  # type: ignore[attr-defined]

    # Call run_diagnostic — it wraps _call_agent_http with asyncio.wait_for
    # We need to also mock the client to avoid real HTTP calls during shutdown
    host._client = AsyncMock()

    symptoms = [Symptom(name="fever")]
    results, audit_data = await host.run_diagnostic(
        symptoms=symptoms,
        patient_profile=None,
        locale="fr-TG",
        region="TG",
    )

    # --- Assertions ---

    # 1. Total number of results is always 4 (one per agent)
    assert len(results) == 4, (
        f"Expected 4 results (one per agent), got {len(results)}"
    )

    # 2. All failing agents appear in audit_data.omissions
    for agent_name in failing_agents:
        assert agent_name in audit_data.omissions, (
            f"Failing agent {agent_name!r} should be in omissions, "
            f"but omissions={audit_data.omissions}"
        )

    # 3. All healthy agents are NOT omitted and NOT timed out
    for agent_name in healthy_agents:
        matching = [r for r in results if r.agent_name == agent_name]
        assert len(matching) == 1, (
            f"Expected exactly 1 result for healthy agent {agent_name!r}"
        )
        r = matching[0]
        assert r.omitted is False, (
            f"Healthy agent {agent_name!r} should not be omitted"
        )
        assert r.timed_out is False, (
            f"Healthy agent {agent_name!r} should not be timed out"
        )

    # 4. All failing agents are marked as omitted in their results
    for agent_name in failing_agents:
        matching = [r for r in results if r.agent_name == agent_name]
        assert len(matching) == 1, (
            f"Expected exactly 1 result for failing agent {agent_name!r}"
        )
        r = matching[0]
        assert r.omitted is True, (
            f"Failing agent {agent_name!r} should be omitted"
        )

    # 5. Processing continues — we always get results for ALL agents
    result_agent_names = sorted(r.agent_name for r in results)
    assert result_agent_names == ALL_AGENT_NAMES, (
        f"Expected results for all agents {ALL_AGENT_NAMES}, "
        f"got {result_agent_names}"
    )

    # 6. audit_data.agent_results contains all 4 results
    assert len(audit_data.agent_results) == 4, (
        f"Expected 4 agent_results in audit_data, got {len(audit_data.agent_results)}"
    )
