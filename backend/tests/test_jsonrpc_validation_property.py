"""
Property-based tests for JSON-RPC 2.0 envelope validation in BaseMCPServer.

Feature: best-practices-hardening, Properties 5, 6, 7

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

Property 5: Invalid JSON-RPC envelope → -32600
Property 6: Invalid params type → -32602
Property 7: Valid JSON-RPC envelope → dispatched without validation error
"""
from __future__ import annotations

import asyncio

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.agents.mcp_servers.base_server import BaseMCPServer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _echo_handler(arguments: dict) -> dict:
    return {"echo": arguments}


@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    from sse_starlette.sse import AppStatus
    AppStatus.should_exit_event = asyncio.Event()
    yield


@pytest.fixture()
def server() -> BaseMCPServer:
    srv = BaseMCPServer(server_name="test_validation", port=9996)
    srv.register_tool("echo", "Echo tool", {"type": "object"}, handler=_echo_handler)
    srv.register_resource("test://resource", "Test Resource", "A test resource", "text/plain")
    srv.register_prompt("test_prompt", "A test prompt", [{"name": "arg1", "required": True}])
    return srv


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Values that are NOT "2.0"
_st_bad_jsonrpc = st.one_of(
    st.none(),
    st.integers(),
    st.text().filter(lambda s: s != "2.0"),
    st.booleans(),
    st.floats(allow_nan=False),
)

# Values that are not a non-empty string (invalid method)
_st_bad_method = st.one_of(
    st.none(),
    st.integers(),
    st.just(""),
    st.booleans(),
    st.floats(allow_nan=False),
    st.lists(st.integers(), max_size=2),
)

# Values that are not str, int, or None (invalid id)
# Note: bool is a subclass of int in Python, so booleans pass isinstance(x, int).
# We use floats, lists, and dicts which are genuinely invalid id types.
_st_bad_id = st.one_of(
    st.floats(allow_nan=False).filter(lambda f: not isinstance(f, int)),
    st.lists(st.integers(), max_size=2),
    st.dictionaries(st.text(max_size=3), st.integers(), max_size=2),
)

# Values that are not dict or list (invalid params)
_st_bad_params = st.one_of(
    st.integers(),
    st.text(max_size=20),
    st.booleans(),
    st.floats(allow_nan=False),
)

_MCP_METHODS = ["tools/list", "tools/call", "resources/list",
                "resources/read", "prompts/list", "prompts/get"]

_st_valid_method = st.sampled_from(_MCP_METHODS)
_st_valid_id = st.one_of(st.integers(min_value=0, max_value=10000),
                         st.text(min_size=1, max_size=10), st.none())


def _params_for_method(method: str) -> dict:
    """Return valid params for a given MCP method."""
    if method == "tools/call":
        return {"name": "echo", "arguments": {}}
    if method == "resources/read":
        return {"uri": "test://resource"}
    if method == "prompts/get":
        return {"name": "test_prompt"}
    return {}


# ---------------------------------------------------------------------------
# Feature: best-practices-hardening, Property 5: Invalid JSON-RPC envelope → -32600
# Validates: Requirements 12.1, 12.2, 12.4
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(bad_jsonrpc=_st_bad_jsonrpc)
async def test_property_5_bad_jsonrpc_returns_32600(
    server: BaseMCPServer, bad_jsonrpc: object,
) -> None:
    """A request with jsonrpc != '2.0' must return -32600."""
    req = {"jsonrpc": bad_jsonrpc, "method": "tools/list", "id": 1}
    resp = await server._handle_request(req)
    assert resp["error"]["code"] == -32600


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(bad_method=_st_bad_method)
async def test_property_5_bad_method_returns_32600(
    server: BaseMCPServer, bad_method: object,
) -> None:
    """A request with method absent or non-string must return -32600."""
    req: dict = {"jsonrpc": "2.0", "id": 1}
    if bad_method is not None:
        req["method"] = bad_method
    resp = await server._handle_request(req)
    assert resp["error"]["code"] == -32600


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(bad_id=_st_bad_id)
async def test_property_5_bad_id_returns_32600(
    server: BaseMCPServer, bad_id: object,
) -> None:
    """A request with id of invalid type must return -32600."""
    req = {"jsonrpc": "2.0", "method": "tools/list", "id": bad_id}
    resp = await server._handle_request(req)
    assert resp["error"]["code"] == -32600


# ---------------------------------------------------------------------------
# Feature: best-practices-hardening, Property 6: Invalid params type → -32602
# Validates: Requirement 12.3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(bad_params=_st_bad_params)
async def test_property_6_bad_params_returns_32602(
    server: BaseMCPServer, bad_params: object,
) -> None:
    """A request with params of invalid type (not dict/list) must return -32602."""
    req = {"jsonrpc": "2.0", "method": "tools/list", "params": bad_params, "id": 1}
    resp = await server._handle_request(req)
    assert resp["error"]["code"] == -32602


# ---------------------------------------------------------------------------
# Feature: best-practices-hardening, Property 7: Valid JSON-RPC envelope → dispatch
# Validates: Requirement 12.5
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(method=_st_valid_method, req_id=_st_valid_id)
async def test_property_7_valid_envelope_dispatched(
    server: BaseMCPServer, method: str, req_id: object,
) -> None:
    """A valid JSON-RPC envelope must not return -32600 or -32602."""
    params = _params_for_method(method)
    req: dict = {"jsonrpc": "2.0", "method": method, "params": params}
    if req_id is not None:
        req["id"] = req_id
    resp = await server._handle_request(req)
    if "error" in resp:
        assert resp["error"]["code"] not in (-32600, -32602), (
            f"Valid envelope got validation error: {resp['error']}"
        )
