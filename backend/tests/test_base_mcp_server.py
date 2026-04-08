"""
Unit tests for BaseMCPServer — JSON-RPC 2.0 dispatch, SSE responses, error codes.

Validates: Requirements 1.7, 3.2, 3.5, 14.2
"""
from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.agents.mcp_servers.base_server import BaseMCPServer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_sse_response(text: str) -> dict:
    """Extract the JSON-RPC 2.0 payload from an SSE ``data:`` line."""
    for line in text.strip().split("\n"):
        if line.startswith("data:"):
            return json.loads(line[len("data:"):].strip())
    raise ValueError("No data line found in SSE response")


def _jsonrpc_request(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": req_id}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _echo_handler(arguments: dict) -> dict:
    """Simple tool handler that echoes its arguments."""
    return {"echo": arguments}


async def _failing_handler(arguments: dict) -> dict:
    """Tool handler that always raises."""
    raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    """Reset sse-starlette's AppStatus event so it binds to the current loop."""
    from sse_starlette.sse import AppStatus
    AppStatus.should_exit_event = asyncio.Event()
    yield


@pytest.fixture()
def server() -> BaseMCPServer:
    srv = BaseMCPServer(server_name="test", port=9999)
    srv.register_tool("test_tool", "A test tool", {"type": "object"}, handler=_echo_handler)
    srv.register_resource("test://resource", "Test Resource", "A test resource", "text/plain")
    srv.register_prompt("test_prompt", "A test prompt", [{"name": "arg1", "required": True}])
    return srv


# ---------------------------------------------------------------------------
# Discovery tests (Req 1.7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_list(server: BaseMCPServer) -> None:
    """POST /rpc with method 'tools/list' returns registered tools."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/rpc", json=_jsonrpc_request("tools/list"))

    payload = parse_sse_response(resp.text)
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    tools = payload["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "test_tool"
    assert tools[0]["description"] == "A test tool"


@pytest.mark.asyncio
async def test_resources_list(server: BaseMCPServer) -> None:
    """POST /rpc with method 'resources/list' returns registered resources."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/rpc", json=_jsonrpc_request("resources/list"))

    payload = parse_sse_response(resp.text)
    resources = payload["result"]["resources"]
    assert len(resources) == 1
    assert resources[0]["uri"] == "test://resource"
    assert resources[0]["name"] == "Test Resource"


@pytest.mark.asyncio
async def test_prompts_list(server: BaseMCPServer) -> None:
    """POST /rpc with method 'prompts/list' returns registered prompts."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/rpc", json=_jsonrpc_request("prompts/list"))

    payload = parse_sse_response(resp.text)
    prompts = payload["result"]["prompts"]
    assert len(prompts) == 1
    assert prompts[0]["name"] == "test_prompt"
    assert prompts[0]["arguments"] == [{"name": "arg1", "required": True}]


# ---------------------------------------------------------------------------
# Invocation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_call(server: BaseMCPServer) -> None:
    """POST /rpc with method 'tools/call' invokes the handler and returns result."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/rpc",
            json=_jsonrpc_request("tools/call", {"name": "test_tool", "arguments": {"key": "val"}}),
        )

    payload = parse_sse_response(resp.text)
    assert payload["result"] == {"echo": {"key": "val"}}


@pytest.mark.asyncio
async def test_resources_read(server: BaseMCPServer) -> None:
    """POST /rpc with method 'resources/read' returns resource content."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/rpc",
            json=_jsonrpc_request("resources/read", {"uri": "test://resource"}),
        )

    payload = parse_sse_response(resp.text)
    contents = payload["result"]["contents"]
    assert len(contents) == 1
    assert contents[0]["uri"] == "test://resource"
    assert contents[0]["mimeType"] == "text/plain"


@pytest.mark.asyncio
async def test_prompts_get(server: BaseMCPServer) -> None:
    """POST /rpc with method 'prompts/get' returns prompt template."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/rpc",
            json=_jsonrpc_request("prompts/get", {"name": "test_prompt"}),
        )

    payload = parse_sse_response(resp.text)
    result = payload["result"]
    assert result["description"] == "A test prompt"
    assert len(result["messages"]) == 1
    assert result["arguments"] == [{"name": "arg1", "required": True}]


# ---------------------------------------------------------------------------
# SSE response format test (Req 3.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_response_format(server: BaseMCPServer) -> None:
    """Response Content-Type is text/event-stream and data contains valid JSON-RPC 2.0."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/rpc", json=_jsonrpc_request("tools/list"))

    assert "text/event-stream" in resp.headers["content-type"]
    payload = parse_sse_response(resp.text)
    assert payload["jsonrpc"] == "2.0"
    assert "result" in payload
    assert payload["id"] == 1


# ---------------------------------------------------------------------------
# Error code tests (Req 3.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_error_32700(server: BaseMCPServer) -> None:
    """Send invalid JSON, expect error code -32700."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/rpc",
            content=b"{not valid json",
            headers={"Content-Type": "application/json"},
        )

    payload = parse_sse_response(resp.text)
    assert payload["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_invalid_request_32600(server: BaseMCPServer) -> None:
    """Send request without 'jsonrpc' or 'method', expect -32600."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/rpc", json={"id": 1})

    payload = parse_sse_response(resp.text)
    assert payload["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_method_not_found_32601(server: BaseMCPServer) -> None:
    """Send request with unknown method, expect -32601."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/rpc", json=_jsonrpc_request("unknown/method"))

    payload = parse_sse_response(resp.text)
    assert payload["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_invalid_params_32602(server: BaseMCPServer) -> None:
    """Call tools/call without 'name' param, expect -32602."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/rpc",
            json=_jsonrpc_request("tools/call", {"arguments": {}}),
        )

    payload = parse_sse_response(resp.text)
    assert payload["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_internal_error_32603() -> None:
    """Register a tool handler that raises, expect -32603."""
    srv = BaseMCPServer(server_name="test_err", port=9998)
    srv.register_tool("bad_tool", "Fails", {"type": "object"}, handler=_failing_handler)

    transport = ASGITransport(app=srv.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/rpc",
            json=_jsonrpc_request("tools/call", {"name": "bad_tool"}),
        )

    payload = parse_sse_response(resp.text)
    assert payload["error"]["code"] == -32603


# ---------------------------------------------------------------------------
# Health endpoint test (Req 14.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint(server: BaseMCPServer) -> None:
    """GET /health returns {"status": "ok", "server": "test"}."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data == {"status": "ok", "server": "test"}
