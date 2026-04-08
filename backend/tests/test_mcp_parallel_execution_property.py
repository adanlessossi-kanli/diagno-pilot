"""
Property-based test for MCP parallel agent execution.

Feature: guided-diagnosis-multi-agent, Property 17: Exécution parallèle des agents (structurelle)

**Validates: Requirement 15.3**

Property 17: For any call to `MCP_Host.run_diagnostic()`, the 4 agents must
be contacted via `asyncio.gather()` with concurrent HTTP requests (not
sequentially). Verified structurally: with 4 mocked agents each having a
controlled delay of `d` seconds, the total duration must be less than `2 × d`
(and not `4 × d`), confirming parallel execution of HTTP requests.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.models.consultation import Symptom
from backend.services.mcp_host import AgentResult, MCP_Host, _AGENT_URLS


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_AGENT_NAMES = sorted(_AGENT_URLS.keys())


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent
# Property 17: Exécution parallèle des agents (structurelle)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(delay=st.floats(min_value=0.05, max_value=0.2))
async def test_property_17_parallel_execution(delay: float) -> None:
    """Validates: Requirement 15.3

    For any call to MCP_Host.run_diagnostic(), the 4 agents must be contacted
    via asyncio.gather() with concurrent HTTP requests (not sequentially).
    With 4 mocked agents each having a controlled delay of `d` seconds, the
    total duration must be less than 2 × d (and not 4 × d), confirming
    parallel execution of HTTP requests.
    """
    # Create MCP_Host instance with mocked internals
    host = MCP_Host.__new__(MCP_Host)
    host._capability_cache = {}
    host._client = AsyncMock()

    # Mock _call_agent_http to sleep for `delay` then return a valid AgentResult
    async def mock_call_agent_http(
        agent_name: str,
        symptoms: list[Symptom],
        patient_profile: object,
        locale: str,
        region: str | None,
    ) -> AgentResult:
        await asyncio.sleep(delay)
        return AgentResult(
            agent_name=agent_name,
            sub_question=f"Sub-question for {agent_name}",
            chunks=[{
                "document_id": "doc1",
                "title": "Test",
                "source": "src",
                "excerpt": "excerpt",
                "page": 1,
            }],
            confidence_score=0.8,
            partial_differential=[],
            timed_out=False,
            omitted=False,
            fallback_used=False,
        )

    host._call_agent_http = mock_call_agent_http  # type: ignore[attr-defined]

    symptoms = [Symptom(name="fever")]

    # Measure wall-clock time of run_diagnostic
    start = time.perf_counter()
    results, audit_data = await host.run_diagnostic(
        symptoms=symptoms,
        patient_profile=None,
        locale="fr-TG",
        region="TG",
    )
    total_time = time.perf_counter() - start

    # --- Assertions ---

    # 1. All 4 agents must have returned results
    assert len(results) == 4, (
        f"Expected 4 results (one per agent), got {len(results)}"
    )

    # 2. Total time must be less than 2 * delay (parallel execution)
    #    If sequential, total_time would be >= 4 * delay
    assert total_time < 2 * delay, (
        f"Parallel execution violated: total_time={total_time:.4f}s >= "
        f"2 * delay={2 * delay:.4f}s (delay={delay:.4f}s). "
        f"Sequential execution would take ~{4 * delay:.4f}s."
    )

    # 3. All agent names must be present in results
    result_agent_names = sorted(r.agent_name for r in results)
    assert result_agent_names == ALL_AGENT_NAMES, (
        f"Expected results for all agents {ALL_AGENT_NAMES}, "
        f"got {result_agent_names}"
    )

    # 4. No agents should be timed out or omitted
    for r in results:
        assert r.timed_out is False, (
            f"Agent {r.agent_name!r} should not be timed out"
        )
        assert r.omitted is False, (
            f"Agent {r.agent_name!r} should not be omitted"
        )
