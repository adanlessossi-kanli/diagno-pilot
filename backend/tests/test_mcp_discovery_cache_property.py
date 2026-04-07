"""
Property-based test for MCP discovery cache idempotence.

Feature: guided-diagnosis-multi-agent, Property 3: Idempotence du cache de découverte des primitives

**Validates: Requirements 2.2, 2.3, 2.4**

Property 3: For any sequence of N invocations (N >= 1) on the same MCP server,
the discovery requests (tools/list, resources/list, prompts/list) must be sent
only once. Subsequent invocations must use cached primitives without resending
discovery requests. When a server HTTP is unreachable (connection refused,
timeout), the cache must be invalidated and discovery re-launched upon
reconnection.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.services.mcp_host import MCP_Host, MCPCapabilities


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DISCOVERY_METHODS = {"tools/list", "resources/list", "prompts/list"}

# Valid JSON-RPC 2.0 responses for each discovery method
_DISCOVERY_RESPONSES: dict[str, dict] = {
    "tools/list": {"jsonrpc": "2.0", "result": {"tools": [{"name": "query_test"}]}, "id": 1},
    "resources/list": {"jsonrpc": "2.0", "result": {"resources": [{"uri": "test://docs"}]}, "id": 2},
    "prompts/list": {"jsonrpc": "2.0", "result": {"prompts": [{"name": "test_query"}]}, "id": 3},
}


async def _mock_send_rpc(
    self: MCP_Host,
    agent_name: str,
    method: str,
    params: dict,
    request_id: int,
) -> dict:
    """Mock _send_rpc that returns valid discovery responses and tracks calls."""
    # Track the call on the instance (set up by the test)
    self._rpc_call_log.append(method)  # type: ignore[attr-defined]
    if method in _DISCOVERY_RESPONSES:
        return _DISCOVERY_RESPONSES[method]
    return {"jsonrpc": "2.0", "result": {}, "id": request_id}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_st_agent_name = st.sampled_from(["epidemiology", "symptomatology", "lab", "treatment"])
_st_n_invocations = st.integers(min_value=1, max_value=5)


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent, Property 3: Idempotence du cache de découverte
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(agent_name=_st_agent_name, n=_st_n_invocations)
async def test_property_3_discovery_cache_idempotence(
    agent_name: str,
    n: int,
) -> None:
    """Validates: Requirements 2.2, 2.3, 2.4

    For any sequence of N invocations (N >= 1) on the same MCP server, the
    discovery requests (tools/list, resources/list, prompts/list) must be sent
    only once. Subsequent invocations must use cached primitives without
    resending discovery requests. After cache invalidation, discovery must
    happen again exactly once.
    """
    host = MCP_Host.__new__(MCP_Host)
    host._capability_cache = {}
    host._rpc_call_log: list[str] = []  # type: ignore[attr-defined]

    with patch.object(
        MCP_Host, "_send_rpc", new=_mock_send_rpc
    ):
        # --- Phase 1: N invocations — discovery should happen only once ---
        for _ in range(n):
            caps = await host._discover_capabilities(agent_name)

        # Verify we got valid capabilities back
        assert isinstance(caps, MCPCapabilities)
        assert len(caps.tools) == 1
        assert caps.tools[0]["name"] == "query_test"
        assert len(caps.resources) == 1
        assert caps.resources[0]["uri"] == "test://docs"
        assert len(caps.prompts) == 1
        assert caps.prompts[0]["name"] == "test_query"

        # Count discovery method calls — each should be called exactly once
        discovery_calls = [m for m in host._rpc_call_log if m in DISCOVERY_METHODS]
        for method in DISCOVERY_METHODS:
            count = discovery_calls.count(method)
            assert count == 1, (
                f"Expected {method} to be called exactly 1 time after {n} "
                f"invocations, but it was called {count} times"
            )

        # --- Phase 2: Invalidate cache and call again — discovery should re-occur ---
        host._rpc_call_log.clear()
        host._capability_cache.pop(agent_name, None)

        caps2 = await host._discover_capabilities(agent_name)

        assert isinstance(caps2, MCPCapabilities)
        assert len(caps2.tools) == 1

        rediscovery_calls = [m for m in host._rpc_call_log if m in DISCOVERY_METHODS]
        for method in DISCOVERY_METHODS:
            count = rediscovery_calls.count(method)
            assert count == 1, (
                f"Expected {method} to be called exactly 1 time after cache "
                f"invalidation, but it was called {count} times"
            )
