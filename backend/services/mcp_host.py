"""MCP_Host — orchestrates four specialist sub-agents in parallel via MCP stdio transport."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from backend.models.consultation import DifferentialDiagnosis, Symptom
from backend.models.patient import PatientProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — REQ 2.1, 2.10
# ---------------------------------------------------------------------------
AGENT_TIMEOUT = 30  # seconds

SOURCE_FILTERS: dict[str, dict] = {
    "epidemiology": {"metadata.document_type": "epidemiology"},
    "symptomatology": {"metadata.document_type": "guideline"},
    "lab": {"metadata.document_type": "laboratory"},
    "treatment": {"metadata.document_type": {"$in": ["protocol", "guideline"]}},
}

# Maps agent name to its script path
_AGENT_SCRIPTS: dict[str, str] = {
    "epidemiology": "backend/agents/epidemiology_agent.py",
    "symptomatology": "backend/agents/symptomatology_agent.py",
    "lab": "backend/agents/lab_agent.py",
    "treatment": "backend/agents/treatment_agent.py",
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


@dataclass
class DiagnosticAuditData:
    """Audit metadata collected during a diagnostic run — REQ 2.12."""
    timeouts: list[str] = field(default_factory=list)
    omissions: list[str] = field(default_factory=list)
    agent_results: list[AgentResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sub-question builders — REQ 2.2
# ---------------------------------------------------------------------------
def _build_sub_question(
    agent_name: str,
    symptoms: list[Symptom],
    patient_profile: PatientProfile | None,
    locale: str,
    region: str | None,
) -> str:
    """Build a focused sub-question for the given specialist agent."""
    symptom_names = ", ".join(s.name for s in symptoms)
    region_clause = f" dans la région {region}" if region else ""

    templates: dict[str, str] = {
        "epidemiology": (
            f"Quelles sont les données épidémiologiques pertinentes pour les symptômes "
            f"suivants{region_clause} : {symptom_names} ?"
        ),
        "symptomatology": (
            f"Quelles pathologies correspondent aux symptômes suivants selon les guidelines "
            f"cliniques{region_clause} : {symptom_names} ?"
        ),
        "lab": (
            f"Quels examens biologiques et résultats de laboratoire sont indiqués pour "
            f"les symptômes suivants{region_clause} : {symptom_names} ?"
        ),
        "treatment": (
            f"Quels protocoles de traitement sont recommandés pour les symptômes suivants"
            f"{region_clause} : {symptom_names} ?"
        ),
    }
    return templates.get(agent_name, f"Analyse les symptômes : {symptom_names}")


# ---------------------------------------------------------------------------
# MCP_Host — REQ 2.1, 2.10, 2.12
# ---------------------------------------------------------------------------
class MCP_Host:
    """Orchestrates four specialist sub-agents in parallel via MCP stdio transport.

    Each agent is launched as a subprocess. A JSON request is sent via stdin and
    the JSON response is read from stdout. A 30-second timeout is applied per agent
    via :func:`asyncio.wait_for`. Timed-out agents are treated as returning zero
    grounded chunks and their names are recorded in :class:`DiagnosticAuditData`.
    """

    async def _call_agent(
        self,
        agent_name: str,
        sub_question: str,
        source_filter: dict,
        patient_profile: PatientProfile | None,
        locale: str,
        region: str | None,
    ) -> AgentResult:
        """Launch a single agent subprocess and collect its result.

        Sends a JSON request over stdin and reads the JSON response from stdout.
        Returns an :class:`AgentResult` with ``timed_out=True`` and zero chunks
        on :exc:`asyncio.TimeoutError`.
        """
        script_path = _AGENT_SCRIPTS.get(agent_name)
        if script_path is None:
            logger.error("No script registered for agent %r", agent_name)
            return AgentResult(
                agent_name=agent_name,
                sub_question=sub_question,
                omitted=True,
            )

        request_payload = json.dumps(
            {
                "agent_name": agent_name,
                "sub_question": sub_question,
                "source_filter": source_filter,
                "patient_profile": patient_profile.model_dump() if patient_profile else None,
                "locale": locale,
                "region": region,
            }
        ).encode()

        try:
            proc = await asyncio.create_subprocess_exec(
                "python",
                script_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def _communicate() -> AgentResult:
                stdout, stderr = await proc.communicate(input=request_payload)
                if stderr:
                    logger.debug("Agent %r stderr: %s", agent_name, stderr.decode(errors="replace"))
                raw = stdout.decode(errors="replace").strip()
                if not raw:
                    logger.warning("Agent %r returned empty stdout", agent_name)
                    return AgentResult(
                        agent_name=agent_name,
                        sub_question=sub_question,
                        omitted=True,
                    )
                data = json.loads(raw)
                partial_differential = [
                    DifferentialDiagnosis(**d) for d in data.get("partial_differential", [])
                ]
                return AgentResult(
                    agent_name=agent_name,
                    sub_question=sub_question,
                    chunks=data.get("chunks", []),
                    confidence_score=float(data.get("confidence_score", 0.0)),
                    partial_differential=partial_differential,
                    timed_out=False,
                    omitted=False,
                )

            return await asyncio.wait_for(_communicate(), timeout=AGENT_TIMEOUT)

        except asyncio.TimeoutError:
            logger.warning(
                "Agent %r timed out after %ds — treating as zero grounded chunks",
                agent_name,
                AGENT_TIMEOUT,
            )
            try:
                proc.kill()
            except Exception:
                pass
            return AgentResult(
                agent_name=agent_name,
                sub_question=sub_question,
                timed_out=True,
            )
        except Exception as exc:
            logger.error("Agent %r failed with error: %s", agent_name, exc)
            return AgentResult(
                agent_name=agent_name,
                sub_question=sub_question,
                omitted=True,
            )

    async def run_diagnostic(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None,
        locale: str,
        region: str | None,
    ) -> tuple[list[AgentResult], DiagnosticAuditData]:
        """Run all four specialist agents in parallel and collect results.

        Launches ``epidemiology``, ``symptomatology``, ``lab``, and ``treatment``
        agents concurrently via :func:`asyncio.gather`. Each agent is wrapped in
        :func:`asyncio.wait_for` with a 30-second timeout. Timed-out agents
        contribute zero grounded chunks; their names are recorded in
        :class:`DiagnosticAuditData`.

        Args:
            symptoms: List of patient symptoms.
            patient_profile: Optional patient profile for personalised queries.
            locale: BCP-47 locale string (e.g. ``"fr-TG"``).
            region: ISO 3166-1 alpha-2 region code or ``None``.

        Returns:
            A tuple of ``(agent_results, audit_data)`` where ``agent_results``
            contains one :class:`AgentResult` per agent and ``audit_data``
            records timeouts and omissions.
        """
        agent_names = list(SOURCE_FILTERS.keys())

        tasks = [
            self._call_agent(
                agent_name=name,
                sub_question=_build_sub_question(name, symptoms, patient_profile, locale, region),
                source_filter=SOURCE_FILTERS[name],
                patient_profile=patient_profile,
                locale=locale,
                region=region,
            )
            for name in agent_names
        ]

        results: list[AgentResult] = await asyncio.gather(*tasks)

        audit_data = DiagnosticAuditData(agent_results=list(results))
        for result in results:
            if result.timed_out:
                audit_data.timeouts.append(result.agent_name)
                logger.warning("Recorded timeout for agent %r", result.agent_name)
            if result.omitted:
                audit_data.omissions.append(result.agent_name)
                logger.warning("Recorded omission for agent %r", result.agent_name)

        return list(results), audit_data
