"""
Tests for MCP_Host — Diagno-Pilot
Updated for HTTP+SSE JSON-RPC 2.0 architecture.

The SOURCE_FILTERS dict and subprocess-based communication have been removed.
Source filters are now internal to each MCP server. The MCP_Host communicates
via httpx.AsyncClient to POST /rpc endpoints.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.models.consultation import Symptom
from backend.services.mcp_host import MCP_Host, _AGENT_URLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_symptom(name: str) -> Symptom:
    return Symptom(name=name)


def _sse_wrap(payload: dict) -> str:
    """Wrap a JSON-RPC 2.0 response dict as an SSE data: line."""
    return f"data: {json.dumps(payload)}\n\n"


def _jsonrpc_result(result: dict, request_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "result": result, "id": request_id}


# ---------------------------------------------------------------------------
# Unit tests — _AGENT_URLS correctness
# ---------------------------------------------------------------------------

class TestAgentURLs:
    """Verify that _AGENT_URLS contains entries for all 4 agents."""

    def test_agent_urls_has_all_four_agents(self):
        assert set(_AGENT_URLS.keys()) == {"epidemiology", "symptomatology", "lab", "treatment"}

    def test_agent_urls_are_http(self):
        for name, url in _AGENT_URLS.items():
            assert url.startswith("http"), f"Agent {name} URL must start with http: {url}"


# ---------------------------------------------------------------------------
# Unit tests — SSE parsing
# ---------------------------------------------------------------------------

class TestParseSSEResponse:
    """Verify SSE response parsing."""

    def test_parse_single_data_line(self):
        host = MCP_Host()
        text = 'data: {"jsonrpc": "2.0", "result": {"tools": []}, "id": 1}\n\n'
        parsed = host._parse_sse_response(text)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["result"] == {"tools": []}

    def test_parse_no_data_lines_raises(self):
        host = MCP_Host()
        with pytest.raises(ValueError, match="No 'data:' lines"):
            host._parse_sse_response("event: message\n\n")


# ---------------------------------------------------------------------------
# Unit tests — MCP_Host health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    """Verify agent health check behaviour."""

    @pytest.mark.asyncio
    async def test_healthy_agent(self):
        host = MCP_Host()
        mock_response = httpx.Response(200, json={"status": "ok"})
        host._client.get = AsyncMock(return_value=mock_response)
        assert await host._check_agent_health("epidemiology") is True
        await host.shutdown()

    @pytest.mark.asyncio
    async def test_unhealthy_agent_connect_error(self):
        host = MCP_Host()
        host._client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        assert await host._check_agent_health("epidemiology") is False
        await host.shutdown()

    @pytest.mark.asyncio
    async def test_unhealthy_agent_timeout(self):
        host = MCP_Host()
        host._client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        assert await host._check_agent_health("epidemiology") is False
        await host.shutdown()


# ---------------------------------------------------------------------------
# Unit tests — run_diagnostic with mocked HTTP
# ---------------------------------------------------------------------------

class TestRunDiagnosticHTTP:
    """Verify run_diagnostic orchestrates all 4 agents via HTTP."""

    @pytest.mark.asyncio
    async def test_all_agents_unreachable_returns_omitted(self):
        """When all agents fail health check, all results should be omitted."""
        host = MCP_Host()
        host._check_agent_health = AsyncMock(return_value=False)

        symptoms = [_make_symptom("fever")]
        results, audit = await host.run_diagnostic(symptoms, None, "fr-TG", None)

        assert len(results) == 4
        for r in results:
            assert r.omitted is True
        assert len(audit.omissions) == 4
        await host.shutdown()

    @pytest.mark.asyncio
    async def test_all_agents_healthy_returns_results(self):
        """When all agents respond correctly, results should be populated."""
        host = MCP_Host()

        # Mock health check to pass
        host._check_agent_health = AsyncMock(return_value=True)

        # Mock _send_rpc to return appropriate responses for each method
        call_count = {}

        async def mock_send_rpc(agent_name, method, params, request_id):
            call_count.setdefault(agent_name, []).append(method)
            if method == "tools/list":
                return _jsonrpc_result({"tools": [{"name": f"query_{agent_name}"}]})
            elif method == "resources/list":
                return _jsonrpc_result({"resources": [{"uri": f"{agent_name}://documents"}]})
            elif method == "prompts/list":
                return _jsonrpc_result({"prompts": [{"name": f"{agent_name}_query"}]})
            elif method == "prompts/get":
                return _jsonrpc_result({"description": f"Query for {agent_name}"})
            elif method == "resources/read":
                return _jsonrpc_result({"contents": []})
            elif method == "tools/call":
                return _jsonrpc_result({
                    "agent_name": agent_name,
                    "sub_question": f"Sub-question for {agent_name}",
                    "chunks": [{"document_id": "doc1", "title": "Test"}],
                    "confidence_score": 0.85,
                    "partial_differential": [],
                    "fallback_used": False,
                })
            return _jsonrpc_result({})

        host._send_rpc = mock_send_rpc

        symptoms = [_make_symptom("fever"), _make_symptom("headache")]
        results, audit = await host.run_diagnostic(symptoms, None, "fr-TG", "TG")

        assert len(results) == 4
        for r in results:
            assert r.timed_out is False
            assert r.omitted is False
            assert len(r.chunks) == 1
            assert r.confidence_score == 0.85
        assert len(audit.timeouts) == 0
        assert len(audit.omissions) == 0
        await host.shutdown()

# ---------------------------------------------------------------------------
# Unit tests — Timeout behaviour (REQ 2.7, 2.8, 2.10)
# ---------------------------------------------------------------------------

class TestTimeout:
    """Verify the 30s timeout wrapping around _call_agent_http."""

    @pytest.mark.asyncio
    async def test_agent_timeout_returns_timed_out_result(self):
        """When an agent exceeds the timeout, result has timed_out=True
        and audit_data records the timeout."""
        host = MCP_Host()

        # Make _call_agent_http hang longer than the timeout
        async def _slow_call(*_args, **_kwargs):
            await asyncio.sleep(10)  # will be cancelled by wait_for

        host._call_agent_http = _slow_call

        symptoms = [_make_symptom("fever")]

        # Use a very small timeout to avoid slow tests
        import backend.services.mcp_host as mcp_mod
        original_timeout = mcp_mod.AGENT_TIMEOUT
        mcp_mod.AGENT_TIMEOUT = 0.05  # 50ms

        try:
            results, audit = await host.run_diagnostic(symptoms, None, "fr-TG", None)
        finally:
            mcp_mod.AGENT_TIMEOUT = original_timeout

        assert len(results) == 4
        for r in results:
            assert r.timed_out is True
        # All 4 agents should appear in audit timeouts
        assert len(audit.timeouts) == 4
        await host.shutdown()


# ---------------------------------------------------------------------------
# Unit tests — Cache invalidation (REQ 2.9, 3.6)
# ---------------------------------------------------------------------------

class TestCacheInvalidation:
    """Verify capability cache is invalidated when an agent is unreachable."""

    @pytest.mark.asyncio
    async def test_cache_invalidated_on_connect_error(self):
        """Pre-populated cache entry is removed when health check fails."""
        host = MCP_Host()

        # Pre-populate cache
        from backend.services.mcp_host import MCPCapabilities
        host._capability_cache["epidemiology"] = MCPCapabilities(
            tools=[{"name": "query_epidemiology"}],
            resources=[],
            prompts=[],
        )
        assert "epidemiology" in host._capability_cache

        # Mock health check to fail (simulates ConnectError)
        host._check_agent_health = AsyncMock(return_value=False)

        symptoms = [_make_symptom("fever")]
        results, audit = await host.run_diagnostic(symptoms, None, "fr-TG", None)

        # Cache should be invalidated for all agents (all fail health check)
        assert "epidemiology" not in host._capability_cache
        await host.shutdown()

    @pytest.mark.asyncio
    async def test_cache_invalidated_on_timeout_error(self):
        """Cache entry is removed when _call_agent_http raises httpx.TimeoutException."""
        host = MCP_Host()

        from backend.services.mcp_host import MCPCapabilities
        host._capability_cache["lab"] = MCPCapabilities(
            tools=[{"name": "query_lab"}],
            resources=[],
            prompts=[],
        )
        assert "lab" in host._capability_cache

        # Mock health check to pass, but _send_rpc raises TimeoutException
        host._check_agent_health = AsyncMock(return_value=True)
        host._send_rpc = AsyncMock(
            side_effect=httpx.TimeoutException("read timed out")
        )

        symptoms = [_make_symptom("cough")]
        results, audit = await host.run_diagnostic(symptoms, None, "en", None)

        # All agents should be omitted (TimeoutException caught in _call_agent_http)
        assert "lab" not in host._capability_cache
        for r in results:
            assert r.omitted is True
        await host.shutdown()


# ---------------------------------------------------------------------------
# Unit tests — JSON-RPC 2.0 error handling (REQ 3.5, 3.6)
# ---------------------------------------------------------------------------

class TestJsonRpcErrorHandling:
    """Verify _send_rpc raises on JSON-RPC 2.0 errors and HTTP errors."""

    @pytest.mark.asyncio
    async def test_send_rpc_raises_on_jsonrpc_error(self):
        """A JSON-RPC 2.0 error response should raise RuntimeError."""
        host = MCP_Host()

        error_payload = {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": "Method not found"},
            "id": 1,
        }
        sse_text = _sse_wrap(error_payload)
        mock_response = httpx.Response(
            200,
            text=sse_text,
            request=httpx.Request("POST", "http://fake/rpc"),
        )
        host._client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(RuntimeError, match="JSON-RPC error"):
            await host._send_rpc("epidemiology", "tools/list", {}, 1)

        await host.shutdown()

    @pytest.mark.asyncio
    async def test_send_rpc_raises_on_http_error(self):
        """An HTTP error (e.g. 503) should propagate as httpx.HTTPStatusError."""
        host = MCP_Host()

        from unittest.mock import MagicMock
        mock_request = MagicMock(spec=httpx.Request)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 503
        host._client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                message="Service Unavailable",
                request=mock_request,
                response=mock_resp,
            )
        )

        with pytest.raises(httpx.HTTPStatusError):
            await host._send_rpc("epidemiology", "tools/list", {}, 1)

        await host.shutdown()


# ---------------------------------------------------------------------------
# Unit tests — _send_rpc parsing (REQ 3.1)
# ---------------------------------------------------------------------------

class TestSendRpc:
    """Verify _send_rpc correctly parses a valid SSE response."""

    @pytest.mark.asyncio
    async def test_send_rpc_parses_valid_sse_response(self):
        """A valid SSE response should be parsed into the JSON-RPC 2.0 dict."""
        host = MCP_Host()

        payload = _jsonrpc_result({"tools": [{"name": "query_epidemiology"}]})
        sse_text = _sse_wrap(payload)
        mock_response = httpx.Response(
            200,
            text=sse_text,
            request=httpx.Request("POST", "http://fake/rpc"),
        )
        host._client.post = AsyncMock(return_value=mock_response)

        result = await host._send_rpc("epidemiology", "tools/list", {}, 1)

        assert result["jsonrpc"] == "2.0"
        assert result["result"]["tools"] == [{"name": "query_epidemiology"}]
        assert result["id"] == 1
        await host.shutdown()


# ---------------------------------------------------------------------------
# Unit tests — Mixed agent results (REQ 2.10, 14.1)
# ---------------------------------------------------------------------------

class TestMixedAgentResults:
    """Verify partial agent failure: some healthy, some failing."""

    @pytest.mark.asyncio
    async def test_partial_agent_failure_continues_processing(self):
        """2 healthy + 2 failing agents → 4 results, 2 omitted, 2 healthy."""
        host = MCP_Host()

        # epidemiology and symptomatology healthy; lab and treatment fail
        async def mock_health(agent_name: str) -> bool:
            return agent_name in ("epidemiology", "symptomatology")

        host._check_agent_health = mock_health

        # Mock _send_rpc for healthy agents
        async def mock_send_rpc(agent_name, method, params, request_id):
            if method == "tools/list":
                return _jsonrpc_result({"tools": [{"name": f"query_{agent_name}"}]})
            elif method == "resources/list":
                return _jsonrpc_result({"resources": [{"uri": f"{agent_name}://documents"}]})
            elif method == "prompts/list":
                return _jsonrpc_result({"prompts": [{"name": f"{agent_name}_query"}]})
            elif method == "prompts/get":
                return _jsonrpc_result({"description": f"Query for {agent_name}"})
            elif method == "resources/read":
                return _jsonrpc_result({"contents": []})
            elif method == "tools/call":
                return _jsonrpc_result({
                    "agent_name": agent_name,
                    "sub_question": f"Sub-question for {agent_name}",
                    "chunks": [{"document_id": "doc1", "title": "Test"}],
                    "confidence_score": 0.9,
                    "partial_differential": [],
                    "fallback_used": False,
                })
            return _jsonrpc_result({})

        host._send_rpc = mock_send_rpc

        symptoms = [_make_symptom("fever")]
        results, audit = await host.run_diagnostic(symptoms, None, "fr-TG", "TG")

        assert len(results) == 4

        healthy_results = [r for r in results if not r.omitted]
        omitted_results = [r for r in results if r.omitted]

        assert len(healthy_results) == 2
        assert len(omitted_results) == 2

        # Healthy agents should have data
        for r in healthy_results:
            assert r.agent_name in ("epidemiology", "symptomatology")
            assert r.timed_out is False
            assert len(r.chunks) == 1
            assert r.confidence_score == 0.9

        # Omitted agents should be lab and treatment
        omitted_names = {r.agent_name for r in omitted_results}
        assert omitted_names == {"lab", "treatment"}

        # Audit should reflect omissions
        assert len(audit.omissions) == 2
        assert set(audit.omissions) == {"lab", "treatment"}
        assert len(audit.timeouts) == 0

        await host.shutdown()
