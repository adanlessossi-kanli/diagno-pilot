"""Base MCP Server — JSON-RPC 2.0 over HTTP+SSE.

Provides :class:`BaseMCPServer`, the foundation for all specialist MCP servers.
Handles JSON-RPC 2.0 request dispatch for the six standard MCP methods
(``tools/list``, ``tools/call``, ``resources/list``, ``resources/read``,
``prompts/list``, ``prompts/get``) and returns responses as Server-Sent Events.

Requirements: 1.7, 3.1, 3.2, 3.3, 14.2
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 error codes
# ---------------------------------------------------------------------------
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# ---------------------------------------------------------------------------
# MCP primitive definitions
# ---------------------------------------------------------------------------
@dataclass
class MCPToolDefinition:
    """Registered MCP tool."""

    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Any]


@dataclass
class MCPResourceDefinition:
    """Registered MCP resource."""

    uri: str
    name: str
    description: str
    mime_type: str


@dataclass
class MCPPromptDefinition:
    """Registered MCP prompt template."""

    name: str
    description: str
    arguments: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# BaseMCPServer
# ---------------------------------------------------------------------------
class BaseMCPServer:
    """Base class for MCP specialist servers.

    Manages the JSON-RPC 2.0 protocol over HTTP+SSE:
    - Receives JSON-RPC 2.0 requests via HTTP POST on ``/rpc``
    - Dispatches to ``tools/list``, ``resources/list``, ``prompts/list``,
      ``tools/call``, ``resources/read``, ``prompts/get``
    - Returns JSON-RPC 2.0 responses via SSE (``text/event-stream``)
    - Exposes ``GET /health`` for readiness checks
    """

    def __init__(self, server_name: str, port: int) -> None:
        self.server_name = server_name
        self.port = port
        self._tools: list[MCPToolDefinition] = []
        self._resources: list[MCPResourceDefinition] = []
        self._prompts: list[MCPPromptDefinition] = []
        self._app = FastAPI(title=f"MCP Server - {server_name}")
        self._setup_routes()

    # -- public properties ---------------------------------------------------

    @property
    def app(self) -> FastAPI:
        """Return the underlying FastAPI application (useful for testing)."""
        return self._app

    # -- registration helpers ------------------------------------------------

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: Callable[..., Any],
    ) -> None:
        """Register an MCP tool with its async handler."""
        self._tools.append(
            MCPToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                handler=handler,
            )
        )

    def register_resource(
        self,
        uri: str,
        name: str,
        description: str,
        mime_type: str,
    ) -> None:
        """Register an MCP resource."""
        self._resources.append(
            MCPResourceDefinition(
                uri=uri,
                name=name,
                description=description,
                mime_type=mime_type,
            )
        )

    def register_prompt(
        self,
        name: str,
        description: str,
        arguments: list[dict],
    ) -> None:
        """Register an MCP prompt template."""
        self._prompts.append(
            MCPPromptDefinition(
                name=name,
                description=description,
                arguments=arguments,
            )
        )

    # -- route setup ---------------------------------------------------------

    def _setup_routes(self) -> None:
        """Configure FastAPI routes: ``POST /rpc`` and ``GET /health``."""
        server = self  # capture for closures

        @self._app.post("/rpc")
        async def handle_rpc(request: Request) -> EventSourceResponse:
            try:
                body = await request.json()
            except Exception:
                error_resp = _jsonrpc_error(None, PARSE_ERROR, "Parse error")
                return EventSourceResponse(server._sse_generator(error_resp))

            response = await server._handle_request(body)
            return EventSourceResponse(server._sse_generator(response))

        @self._app.get("/health")
        async def health() -> dict:
            return {"status": "ok", "server": server.server_name}

    # -- JSON-RPC 2.0 dispatch -----------------------------------------------

    async def _handle_request(self, request: dict) -> dict:
        """Dispatch a JSON-RPC 2.0 request to the appropriate handler."""
        # Validate basic structure
        if not isinstance(request, dict):
            return _jsonrpc_error(None, INVALID_REQUEST, "Invalid Request")

        jsonrpc = request.get("jsonrpc")
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        if jsonrpc != "2.0" or not method:
            return _jsonrpc_error(req_id, INVALID_REQUEST, "Invalid Request")

        dispatch: dict[str, Callable[..., Any]] = {
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "prompts/list": self._handle_prompts_list,
            "prompts/get": self._handle_prompts_get,
        }

        handler = dispatch.get(method)
        if handler is None:
            return _jsonrpc_error(req_id, METHOD_NOT_FOUND, "Method not found")

        try:
            result = await handler(params)
            return _jsonrpc_result(req_id, result)
        except InvalidParamsError as exc:
            return _jsonrpc_error(req_id, INVALID_PARAMS, str(exc))
        except Exception as exc:
            logger.exception("Internal error handling method %s", method)
            return _jsonrpc_error(req_id, INTERNAL_ERROR, f"Internal error: {exc}")

    # -- method handlers -----------------------------------------------------

    async def _handle_tools_list(self, _params: dict) -> dict:
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.input_schema,
                }
                for t in self._tools
            ]
        }

    async def _handle_tools_call(self, params: dict) -> dict:
        tool_name = params.get("name")
        if not tool_name:
            raise InvalidParamsError("Missing required param 'name'")

        tool = next((t for t in self._tools if t.name == tool_name), None)
        if tool is None:
            raise InvalidParamsError(f"Unknown tool: {tool_name}")

        arguments = params.get("arguments", {})
        result = await tool.handler(arguments)
        return result

    async def _handle_resources_list(self, _params: dict) -> dict:
        return {
            "resources": [
                {
                    "uri": r.uri,
                    "name": r.name,
                    "description": r.description,
                    "mimeType": r.mime_type,
                }
                for r in self._resources
            ]
        }

    async def _handle_resources_read(self, params: dict) -> dict:
        uri = params.get("uri")
        if not uri:
            raise InvalidParamsError("Missing required param 'uri'")

        resource = next((r for r in self._resources if r.uri == uri), None)
        if resource is None:
            raise InvalidParamsError(f"Unknown resource URI: {uri}")

        content = await self.read_resource(uri)
        return {"contents": [{"uri": uri, "mimeType": resource.mime_type, **content}]}

    async def _handle_prompts_list(self, _params: dict) -> dict:
        return {
            "prompts": [
                {
                    "name": p.name,
                    "description": p.description,
                    "arguments": p.arguments,
                }
                for p in self._prompts
            ]
        }

    async def _handle_prompts_get(self, params: dict) -> dict:
        prompt_name = params.get("name")
        if not prompt_name:
            raise InvalidParamsError("Missing required param 'name'")

        prompt = next((p for p in self._prompts if p.name == prompt_name), None)
        if prompt is None:
            raise InvalidParamsError(f"Unknown prompt: {prompt_name}")

        return {
            "description": prompt.description,
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": prompt.description},
                }
            ],
            "arguments": prompt.arguments,
        }

    # -- resource reading (override in subclasses) ---------------------------

    async def read_resource(self, uri: str) -> dict:
        """Read resource content by URI. Override in subclasses.

        Returns a dict with at least a ``text`` key.
        """
        return {"text": ""}

    # -- SSE generator -------------------------------------------------------

    async def _sse_generator(self, response: dict) -> AsyncGenerator[dict, None]:
        """Yield a single SSE event containing the JSON-RPC 2.0 response."""
        yield {"data": json.dumps(response)}

    # -- server start --------------------------------------------------------

    def run(self) -> None:
        """Start the FastAPI app via uvicorn on the configured port."""
        import uvicorn

        uvicorn.run(self._app, host="0.0.0.0", port=self.port)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class InvalidParamsError(Exception):
    """Raised when JSON-RPC params are invalid."""


def _jsonrpc_result(req_id: Any, result: Any) -> dict:
    """Build a JSON-RPC 2.0 success response."""
    return {"jsonrpc": "2.0", "result": result, "id": req_id}


def _jsonrpc_error(req_id: Any, code: int, message: str) -> dict:
    """Build a JSON-RPC 2.0 error response."""
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id}
