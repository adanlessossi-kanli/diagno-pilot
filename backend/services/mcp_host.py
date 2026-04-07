"""MCP_Host — orchestrates four specialist MCP servers in parallel via HTTP+SSE JSON-RPC 2.0."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

import httpx

from backend.core.config import settings
from backend.models.consultation import DifferentialDiagnosis, Symptom
from backend.models.patient import PatientProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — REQ 2.1, 2.10
# ---------------------------------------------------------------------------
AGENT_TIMEOUT = 30  # seconds

# Agent URLs read from settings (REQ 14.3)
_AGENT_URLS: dict[str, str] = {
    "epidemiology": settings.AGENT_EPIDEMIOLOGY_URL,
    "symptomatology": settings.AGENT_SYMPTOMATOLOGY_URL,
    "lab": settings.AGENT_LAB_URL,
    "treatment": settings.AGENT_TREATMENT_URL,
}


# ---------------------------------------------------------------------------
# Data classes — REQ 2.1, 2.12
# ---------------------------------------------------------------------------
@dataclass
class AgentResult:
    """Result produced by a single specialist sub-agent."""
    agent_name: str
    sub_question: str
    chunks: list[dict] = field(default_factory=list)
    confidence_score: float = 0.0
    partial_differential: list[DifferentialDiagnosis] = field(default_factory=list)
    timed_out: bool = False
    omitted: bool = False
    fallback_used: bool = False


@dataclass
class DiagnosticAuditData:
    """Audit metadata collected during a diagnostic run — REQ 2.12."""
    timeouts: list[str] = field(default_factory=list)
    omissions: list[str] = field(default_factory=list)
    agent_results: list[AgentResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# MCP support dataclasses — REQ 2.2, 3.1
# ---------------------------------------------------------------------------
@dataclass
class MCPCapabilities:
    """Discovered and cached primitives for an MCP server."""
    tools: list[dict] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    prompts: list[dict] = field(default_factory=list)


@dataclass
class MCPRequest:
    """Outgoing JSON-RPC 2.0 request via HTTP POST."""
    method: str
    params: dict
    id: int

    def to_json(self) -> str:
        return json.dumps({
            "jsonrpc": "2.0",
            "method": self.method,
            "params": self.params,
            "id": self.id,
        })


# ---------------------------------------------------------------------------
# MCP_Host — REQ 2.1, 2.10, 2.12, 3.1, 14.1, 14.3
# ---------------------------------------------------------------------------
class MCP_Host:
    """Orchestrates four specialist MCP servers in parallel via HTTP+SSE JSON-RPC 2.0.

    Each agent is a Docker service exposing ``POST /rpc`` (JSON-RPC 2.0) and
    ``GET /health``. Communication uses ``httpx.AsyncClient`` with connection
    pooling. A 30-second timeout covers the entire per-agent sequence (health
    check → discovery → invocation).
    """

    def __init__(self) -> None:
        self._capability_cache: dict[str, MCPCapabilities] = {}
        self._client: httpx.AsyncClient = httpx.AsyncClient(timeout=AGENT_TIMEOUT)

    # ------------------------------------------------------------------
    # SSE parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_sse_response(text: str) -> dict:
        """Parse SSE ``data:`` lines to extract the JSON-RPC 2.0 response.

        The server returns ``text/event-stream`` with one or more ``data:``
        lines. We concatenate the data payloads and parse the last complete
        JSON object found.
        """
        data_parts: list[str] = []
        for line in text.splitlines():
            if line.startswith("data:"):
                data_parts.append(line[len("data:"):].strip())
        if not data_parts:
            raise ValueError("No 'data:' lines found in SSE response")
        raw = " ".join(data_parts)
        return json.loads(raw)

    # ------------------------------------------------------------------
    # Health check — REQ 14.1
    # ------------------------------------------------------------------
    async def _check_agent_health(self, agent_name: str) -> bool:
        """Verify agent availability via ``GET /health`` with a 5s timeout."""
        url = f"{_AGENT_URLS[agent_name]}/health"
        try:
            resp = await self._client.get(url, timeout=5.0)
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 transport — REQ 3.1
    # ------------------------------------------------------------------
    async def _send_rpc(
        self,
        agent_name: str,
        method: str,
        params: dict,
        request_id: int,
    ) -> dict:
        """Send a JSON-RPC 2.0 request via HTTP POST and parse the SSE response."""
        url = f"{_AGENT_URLS[agent_name]}/rpc"
        payload = MCPRequest(method=method, params=params, id=request_id).to_json()
        resp = await self._client.post(
            url,
            content=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        parsed = self._parse_sse_response(resp.text)
        if "error" in parsed:
            raise RuntimeError(
                f"JSON-RPC error from {agent_name}: "
                f"code={parsed['error'].get('code')}, "
                f"message={parsed['error'].get('message')}"
            )
        return parsed

    # ------------------------------------------------------------------
    # Capability discovery — REQ 2.2, 2.3, 2.4
    # ------------------------------------------------------------------
    async def _discover_capabilities(self, agent_name: str) -> MCPCapabilities:
        """Discover tools, resources and prompts for *agent_name*, caching the result.

        If the capabilities are already cached, returns immediately (REQ 2.3).
        """
        if agent_name in self._capability_cache:
            return self._capability_cache[agent_name]

        tools_resp = await self._send_rpc(agent_name, "tools/list", {}, 1)
        resources_resp = await self._send_rpc(agent_name, "resources/list", {}, 2)
        prompts_resp = await self._send_rpc(agent_name, "prompts/list", {}, 3)

        caps = MCPCapabilities(
            tools=tools_resp.get("result", {}).get("tools", []),
            resources=resources_resp.get("result", {}).get("resources", []),
            prompts=prompts_resp.get("result", {}).get("prompts", []),
        )
        self._capability_cache[agent_name] = caps
        return caps

    # ------------------------------------------------------------------
    # Full agent call — REQ 2.5, 2.6, 2.7, 2.8, 9.1
    # ------------------------------------------------------------------
    async def _call_agent_http(
        self,
        agent_name: str,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None,
        locale: str,
        region: str | None,
    ) -> AgentResult:
        """Execute the full MCP sequence for a single agent.

        Sequence (all within a single 30s timeout):
        1. Health check
        2. Discover capabilities (if not cached)
        3. prompts/get — obtain the query template
        4. resources/read — obtain documentary context
        5. tools/call — invoke the specialist tool
        6. Parse the AgentResult from the JSON-RPC 2.0 response
        """
        sub_question = ""
        try:
            # 1. Health check
            healthy = await self._check_agent_health(agent_name)
            if not healthy:
                logger.warning("Agent %r failed health check", agent_name)
                self._capability_cache.pop(agent_name, None)
                return AgentResult(
                    agent_name=agent_name,
                    sub_question="",
                    omitted=True,
                )

            # 2. Discover capabilities (cached after first call)
            caps = await self._discover_capabilities(agent_name)

            # 3. prompts/get — get the query template
            prompt_name = caps.prompts[0]["name"] if caps.prompts else f"{agent_name}_query"
            prompt_resp = await self._send_rpc(
                agent_name,
                "prompts/get",
                {
                    "name": prompt_name,
                    "arguments": {
                        "symptoms": [s.model_dump() for s in symptoms],
                        "patient_profile": patient_profile.model_dump() if patient_profile else None,
                        "locale": locale,
                        "region": region,
                    },
                },
                4,
            )
            prompt_result = prompt_resp.get("result", {})
            sub_question = prompt_result.get("description", "")

            # 4. resources/read — get documentary context
            if caps.resources:
                resource_uri = caps.resources[0].get("uri", "")
                await self._send_rpc(
                    agent_name,
                    "resources/read",
                    {"uri": resource_uri},
                    5,
                )

            # 5. tools/call — invoke the specialist tool
            tool_name = caps.tools[0]["name"] if caps.tools else f"query_{agent_name}"
            tool_resp = await self._send_rpc(
                agent_name,
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": {
                        "symptoms": [s.model_dump() for s in symptoms],
                        "patient_profile": patient_profile.model_dump() if patient_profile else None,
                        "locale": locale,
                        "region": region,
                    },
                },
                6,
            )

            # 6. Parse AgentResult from the response
            data = tool_resp.get("result", {})
            partial_differential = [
                DifferentialDiagnosis(**d) for d in data.get("partial_differential", [])
            ]
            return AgentResult(
                agent_name=agent_name,
                sub_question=sub_question or data.get("sub_question", ""),
                chunks=data.get("chunks", []),
                confidence_score=float(data.get("confidence_score", 0.0)),
                partial_differential=partial_differential,
                timed_out=False,
                omitted=False,
                fallback_used=bool(data.get("fallback_used", False)),
            )

        except asyncio.TimeoutError:
            logger.warning(
                "Agent %r timed out after %ds",
                agent_name,
                AGENT_TIMEOUT,
            )
            self._capability_cache.pop(agent_name, None)
            return AgentResult(
                agent_name=agent_name,
                sub_question=sub_question,
                timed_out=True,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(
                "Agent %r unreachable: %s — invalidating cache",
                agent_name,
                exc,
            )
            self._capability_cache.pop(agent_name, None)
            return AgentResult(
                agent_name=agent_name,
                sub_question=sub_question,
                omitted=True,
            )
        except Exception as exc:
            logger.error("Agent %r failed with error: %s", agent_name, exc)
            return AgentResult(
                agent_name=agent_name,
                sub_question=sub_question,
                omitted=True,
            )

    # ------------------------------------------------------------------
    # Public API — REQ 2.1, 15.3
    # ------------------------------------------------------------------
    async def run_diagnostic(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None,
        locale: str,
        region: str | None,
    ) -> tuple[list[AgentResult], DiagnosticAuditData]:
        """Run all four specialist agents in parallel and collect results.

        Each agent call is wrapped in ``asyncio.wait_for`` with a 30-second
        timeout covering the entire sequence (health → discover → invoke).
        Timed-out or failed agents contribute zero grounded chunks; their
        names are recorded in :class:`DiagnosticAuditData`.
        """
        agent_names = list(_AGENT_URLS.keys())

        async def _call_with_timeout(name: str) -> AgentResult:
            try:
                return await asyncio.wait_for(
                    self._call_agent_http(name, symptoms, patient_profile, locale, region),
                    timeout=AGENT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Agent %r timed out after %ds — treating as zero grounded chunks",
                    name,
                    AGENT_TIMEOUT,
                )
                self._capability_cache.pop(name, None)
                return AgentResult(
                    agent_name=name,
                    sub_question="",
                    timed_out=True,
                )

        results: list[AgentResult] = await asyncio.gather(
            *[_call_with_timeout(name) for name in agent_names]
        )

        audit_data = DiagnosticAuditData(agent_results=list(results))
        for result in results:
            if result.timed_out:
                audit_data.timeouts.append(result.agent_name)
                logger.warning("Recorded timeout for agent %r", result.agent_name)
            if result.omitted:
                audit_data.omissions.append(result.agent_name)
                logger.warning("Recorded omission for agent %r", result.agent_name)

        return list(results), audit_data

    # ------------------------------------------------------------------
    # Shutdown — REQ 14.4
    # ------------------------------------------------------------------
    async def shutdown(self) -> None:
        """Close the HTTP client and all active connections."""
        await self._client.aclose()
