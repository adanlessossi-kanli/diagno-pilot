"""
Property-based test for MCP locale passthrough without transformation.

Feature: guided-diagnosis-multi-agent, Property 13: Passthrough de la Locale sans transformation

**Validates: Requirements 9.1, 9.4, 9.5**

Property 13: For any Locale value (BCP-47 string) and any Region value, the
MCP_Host must transmit the Locale and Region to the MCP specialist servers
without any transformation. The values received by the agents in the
`tools/call` arguments must be identical to the values passed to
`run_diagnostic()`.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.models.consultation import Symptom
from backend.services.mcp_host import MCP_Host, _AGENT_URLS


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_AGENT_NAMES = sorted(_AGENT_URLS.keys())


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_st_locale = st.sampled_from(["fr-TG", "fr-BJ", "en"])
_st_region = st.one_of(st.none(), st.sampled_from(["TG", "BJ"]))
_st_symptom_names = st.lists(
    st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
    min_size=1,
    max_size=5,
)


# ---------------------------------------------------------------------------
# Helpers — mock _send_rpc responses
# ---------------------------------------------------------------------------

_DISCOVERY_RESPONSES: dict[str, dict] = {
    "tools/list": {
        "jsonrpc": "2.0",
        "result": {"tools": [{"name": "query_test"}]},
        "id": 1,
    },
    "resources/list": {
        "jsonrpc": "2.0",
        "result": {"resources": [{"uri": "test://docs"}]},
        "id": 2,
    },
    "prompts/list": {
        "jsonrpc": "2.0",
        "result": {"prompts": [{"name": "test_query"}]},
        "id": 3,
    },
    "prompts/get": {
        "jsonrpc": "2.0",
        "result": {"description": "Test sub-question"},
        "id": 4,
    },
    "resources/read": {
        "jsonrpc": "2.0",
        "result": {"contents": [{"text": "doc content"}]},
        "id": 5,
    },
}

_TOOLS_CALL_RESULT: dict = {
    "jsonrpc": "2.0",
    "result": {
        "agent_name": "test",
        "sub_question": "sub-q",
        "chunks": [
            {
                "document_id": "doc1",
                "title": "Test",
                "source": "src",
                "excerpt": "ex",
                "page": 1,
            }
        ],
        "confidence_score": 0.8,
        "partial_differential": [],
        "fallback_used": False,
    },
    "id": 6,
}


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent
# Property 13: Passthrough de la Locale sans transformation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    locale=_st_locale,
    region=_st_region,
    symptom_names=_st_symptom_names,
)
async def test_property_13_locale_passthrough_without_transformation(
    locale: str,
    region: str | None,
    symptom_names: list[str],
) -> None:
    """Validates: Requirements 9.1, 9.4, 9.5

    For any Locale value (BCP-47 string) and any Region value, the MCP_Host
    must transmit the Locale and Region to the MCP specialist servers without
    any transformation. The values received by the agents in the tools/call
    arguments must be identical to the values passed to run_diagnostic().
    """
    # Dict to capture tools/call arguments per agent
    captured_tools_call_args: dict[str, dict] = {}

    # Build the MCP_Host instance
    host = MCP_Host.__new__(MCP_Host)
    host._capability_cache = {}
    host._client = AsyncMock()

    # Mock _check_agent_health to always return True
    async def mock_check_health(agent_name: str) -> bool:
        return True

    host._check_agent_health = mock_check_health  # type: ignore[attr-defined]

    # Mock _send_rpc to return valid responses and capture tools/call args
    async def mock_send_rpc(
        agent_name: str,
        method: str,
        params: dict,
        request_id: int,
    ) -> dict:
        if method in _DISCOVERY_RESPONSES:
            return _DISCOVERY_RESPONSES[method]
        if method == "tools/call":
            # Capture the arguments dict from the params
            captured_tools_call_args[agent_name] = params.get("arguments", {})
            # Return a valid AgentResult response with the correct agent_name
            result = dict(_TOOLS_CALL_RESULT)
            result = {**result, "result": {**result["result"], "agent_name": agent_name}}
            return result
        return {"jsonrpc": "2.0", "result": {}, "id": request_id}

    host._send_rpc = mock_send_rpc  # type: ignore[attr-defined]

    # Build symptoms from generated names
    symptoms = [Symptom(name=name) for name in symptom_names]

    # Call run_diagnostic with the generated locale and region
    results, audit_data = await host.run_diagnostic(
        symptoms=symptoms,
        patient_profile=None,
        locale=locale,
        region=region,
    )

    # --- Assertions ---

    # Every agent must have had its tools/call invoked
    assert len(captured_tools_call_args) == len(ALL_AGENT_NAMES), (
        f"Expected tools/call for all {len(ALL_AGENT_NAMES)} agents, "
        f"but captured for {sorted(captured_tools_call_args.keys())}"
    )

    # For EVERY agent's tools/call invocation, locale and region must be
    # identical to the values passed to run_diagnostic() (no transformation)
    for agent_name, args in captured_tools_call_args.items():
        assert args["locale"] == locale, (
            f"Agent {agent_name!r}: expected locale={locale!r}, "
            f"got {args['locale']!r}"
        )
        assert args["region"] == region, (
            f"Agent {agent_name!r}: expected region={region!r}, "
            f"got {args['region']!r}"
        )
