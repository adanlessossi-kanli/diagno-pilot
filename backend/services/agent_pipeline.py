"""AgentPipeline — in-process multi-agent diagnostic pipeline using LlamaIndex.

Replaces subprocess-based agent communication (stdin/stdout JSON) with
in-process LlamaIndex query engine calls.  Enforces PHI boundary: full PHI
to local Model_Container, BAA stripping for GPT-5 fallback.

Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backend.models.consultation import DifferentialDiagnosis
from backend.models.patient import PatientProfile
from backend.services.audit_service import AuditLogger
from backend.services.baa_controller import BAAController
from backend.services.llamaindex_pipeline import LlamaIndexPipeline
from backend.services.llm_router import LLMRouter
from backend.services.phi_classifier import PHIClassifier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """Result produced by a single specialist agent."""

    agent_name: str
    sub_question: str
    chunks: list[dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    partial_differential: list[DifferentialDiagnosis] = field(default_factory=list)
    endpoint_used: str = ""
    duration_seconds: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# Diagnostic response dataclass
# ---------------------------------------------------------------------------

@dataclass
class DiagnosticResponse:
    """Aggregated response from the agent pipeline."""

    diagnoses: list[DifferentialDiagnosis] = field(default_factory=list)
    confidence_score: float = 0.0
    agent_results: list[AgentResult] = field(default_factory=list)
    fallback_used: bool = False
    degraded_warning: str | None = None


# ---------------------------------------------------------------------------
# Sub-question templates per agent
# ---------------------------------------------------------------------------

_SUB_QUESTIONS: dict[str, str] = {
    "symptomatology": (
        "En contexte de médecine tropicale ouest-africaine (paludisme, fièvre typhoïde, dengue, "
        "méningite, schistosomiase), quels diagnostics différentiels correspondent aux symptômes "
        "suivants : {symptoms}? Considérer la sévérité et la durée des symptômes pour prioriser "
        "les pathologies endémiques de la région {region}. {patient_context}"
    ),
    "epidemiology": (
        "Quelles pathologies endémiques d'Afrique de l'Ouest sont compatibles avec les symptômes : "
        "{symptoms}? Considérer la prévalence régionale, les patterns saisonniers (saison des pluies/"
        "saison sèche), les données d'épidémies récentes spécifiques à la région {region}, "
        "et les guidelines du {guidelines_ref}. {patient_context}"
    ),
    "lab": (
        "Quels examens de laboratoire disponibles en milieu clinique ouest-africain (goutte épaisse/"
        "frottis mince, test de Widal, TDR paludisme, NFS) sont indiqués pour les symptômes : "
        "{symptoms}? Prioriser les tests qui affinent le diagnostic différentiel tropical. "
        "{patient_context}"
    ),
    "treatment": (
        "Quels protocoles de traitement alignés sur les formulaires nationaux ouest-africains et "
        "les guidelines OMS AFRO sont recommandés pour les symptômes : {symptoms}? Tenir compte "
        "des allergies, comorbidités, groupe d'âge et disponibilité régionale des médicaments "
        "dans la région {region}. {patient_context}"
    ),
    "synthesis": (
        "Synthétiser les diagnostics différentiels pour les symptômes : {symptoms} en contexte "
        "ouest-africain. Réconcilier les diagnostics conflictuels entre agents, pondérer les "
        "preuves par qualité de source, et prioriser les conditions à haute morbidité/mortalité "
        "dans le contexte tropical. {patient_context}"
    ),
}


# ---------------------------------------------------------------------------
# AgentPipeline
# ---------------------------------------------------------------------------

class AgentPipeline:
    """In-process multi-agent diagnostic pipeline using LlamaIndex query engines.

    Replaces subprocess-based agent communication with direct calls to
    :class:`LlamaIndexPipeline`.  Each agent applies a ``source_filter``
    for metadata-based retrieval (Req 10.4).

    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
    """

    AGENTS: dict[str, dict[str, Any]] = {
        "symptomatology": {
            "source_filter": {"metadata.document_type": "guideline"},
        },
        "epidemiology": {
            "source_filter": {
                "metadata.document_type": {"$in": ["protocol", "guideline"]},
            },
        },
        "lab": {
            "source_filter": {"metadata.source": {"$regex": "CHU|MSF"}},
        },
        "synthesis": {
            "source_filter": {},
        },
        "treatment": {
            "source_filter": {"metadata.document_type": "protocol"},
        },
    }

    def __init__(
        self,
        pipeline: LlamaIndexPipeline,
        llm_router: LLMRouter,
        audit_logger: AuditLogger | None = None,
        baa_controller: BAAController | None = None,
        phi_classifier: PHIClassifier | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._llm_router = llm_router
        self._audit_logger = audit_logger
        self._baa = baa_controller or BAAController(audit_logger=audit_logger)
        self._phi = phi_classifier or PHIClassifier()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        symptoms: list[dict[str, Any]],
        patient_profile: PatientProfile | None = None,
        region: str | None = None,
    ) -> DiagnosticResponse:
        """Execute all agents in parallel and aggregate results.

        Args:
            symptoms: List of symptom dicts (``{name, severity, duration_days}``).
            patient_profile: Optional patient profile (PHI context).
            region: Region pre-filter (``"TG"``, ``"BJ"``, ``"ALL"``).

        Returns:
            :class:`DiagnosticResponse` with aggregated diagnoses and
            confidence score (arithmetic mean of agent scores).
        """
        symptom_text = ", ".join(
            f"{s.get('name', str(s))} (sévérité={s.get('severity', '?')}, durée={s.get('duration_days', '?')}j)"
            if isinstance(s, dict) else str(s)
            for s in symptoms
        )

        # Build patient_context string from profile (Req 22.2)
        patient_context = ""
        if patient_profile:
            parts: list[str] = []
            if patient_profile.age_group:
                parts.append(f"groupe d'âge: {patient_profile.age_group.value}")
            if patient_profile.weight_kg:
                parts.append(f"poids: {patient_profile.weight_kg} kg")
            if patient_profile.allergies:
                parts.append(f"allergies: {', '.join(patient_profile.allergies)}")
            if patient_profile.comorbidities:
                comorbidities: list[str] = []
                if patient_profile.comorbidities.renal_failure:
                    comorbidities.append("insuffisance rénale")
                if patient_profile.comorbidities.hepatic_failure:
                    comorbidities.append("insuffisance hépatique")
                if comorbidities:
                    parts.append(f"comorbidités: {', '.join(comorbidities)}")
            if parts:
                patient_context = f"Profil patient : {'; '.join(parts)}."

        # Map region to guidelines reference (Req 22.4)
        guidelines_map = {"TG": "CHU Lomé", "BJ": "CHU Abomey-Calavi"}
        guidelines_ref = guidelines_map.get(region, "OMS AFRO / MSF") if region else "OMS AFRO / MSF"

        agent_names = list(self.AGENTS.keys())
        tasks = [
            self._run_agent(
                agent_name=name,
                sub_question=_SUB_QUESTIONS.get(name, "{symptoms}").format(
                    symptoms=symptom_text,
                    region=region or "ALL",
                    patient_context=patient_context,
                    guidelines_ref=guidelines_ref,
                ),
                patient_profile=patient_profile,
                region=region,
            )
            for name in agent_names
        ]

        results_raw = await asyncio.gather(*tasks, return_exceptions=True)  # Req 21.1

        # Convert exceptions to AgentResult with correct agent name (Req 21.2)
        results: list[AgentResult] = []
        for i, r in enumerate(results_raw):
            if isinstance(r, BaseException):
                results.append(AgentResult(
                    agent_name=agent_names[i],
                    sub_question="",
                    error=str(r),
                ))
            else:
                results.append(r)

        return self._aggregate(results)

    # ------------------------------------------------------------------
    # Single agent execution
    # ------------------------------------------------------------------

    async def _run_agent(
        self,
        agent_name: str,
        sub_question: str,
        patient_profile: PatientProfile | None,
        region: str | None,
    ) -> AgentResult:
        """Execute a single agent via LlamaIndex query engine.

        PHI boundary enforcement (Req 10.2, 10.3):
        - Full PHI context is passed when the local Model_Container serves
          the request.
        - If the LLM_Router falls back to GPT-5, BAA stripping is already
          handled inside LLMRouter.generate().

        Logging (Req 10.5): each invocation is logged to AuditLogger with
        agent type, query hash, endpoint used, and duration.
        """
        agent_cfg = self.AGENTS.get(agent_name, {})
        source_filter = agent_cfg.get("source_filter")

        t0 = time.perf_counter()
        try:
            rag_response = await self._pipeline.query(
                question=sub_question,
                context=patient_profile,
                region=region,
                source_filter=source_filter,
            )

            # Fallback: retry without source_filter when filtered retrieval yields no sources
            if not rag_response.sources and source_filter:
                logger.info(
                    "Agent %r: filtered retrieval empty, retrying without source_filter",
                    agent_name,
                )
                rag_response = await self._pipeline.query(
                    question=sub_question,
                    context=patient_profile,
                    region=region,
                    source_filter=None,
                )

            endpoint_used = self._llm_router.last_used
            duration = time.perf_counter() - t0

            chunks = [
                {
                    "document_id": s.document_id,
                    "title": s.title,
                    "source": s.source,
                    "excerpt": s.excerpt,
                    "page": s.page,
                }
                for s in rag_response.sources
            ]

            partial_differential = _parse_partial_differential(
                rag_response.answer
            )

            result = AgentResult(
                agent_name=agent_name,
                sub_question=sub_question,
                chunks=chunks,
                confidence_score=rag_response.confidence_score or 0.0,
                partial_differential=partial_differential,
                endpoint_used=endpoint_used,
                duration_seconds=duration,
            )

        except Exception as exc:
            duration = time.perf_counter() - t0
            logger.error(
                "Agent %r failed after %.2fs: %s", agent_name, duration, exc
            )
            result = AgentResult(
                agent_name=agent_name,
                sub_question=sub_question,
                confidence_score=0.0,
                endpoint_used=self._llm_router.last_used,
                duration_seconds=duration,
                error=str(exc),
            )

        # Audit logging (Req 10.5) — best-effort, never fails the agent
        await self._log_agent_invocation(result)

        return result

    # ------------------------------------------------------------------
    # Aggregation (Req 10.6)
    # ------------------------------------------------------------------

    def _aggregate(self, results: list[AgentResult]) -> DiagnosticResponse:
        """Aggregate agent results into a single DiagnosticResponse.

        - Confidence score = arithmetic mean of individual agent scores.
        - All partial differentials are merged (deduplicated by condition
          name, keeping the highest probability).
        - Agents with errors are noted in degraded_warning.
        """
        active = [r for r in results if r.error is None and r.chunks]
        failed = [r for r in results if r.error is not None]

        # Merge partial differentials (dedup by condition, keep highest prob)
        merged: dict[str, DifferentialDiagnosis] = {}
        for r in active:
            for diag in r.partial_differential:
                key = diag.condition.strip().lower()
                existing = merged.get(key)
                if existing is None or diag.probability > existing.probability:
                    merged[key] = diag

        diagnoses = sorted(
            merged.values(), key=lambda d: d.probability, reverse=True
        )

        # Confidence = arithmetic mean of agent scores (Req 10.6)
        scores = [r.confidence_score for r in results if r.error is None]
        confidence = sum(scores) / len(scores) if scores else 0.0

        # Degraded warning for failed agents
        degraded_warning: str | None = None
        if failed:
            names = ", ".join(r.agent_name for r in failed)
            degraded_warning = f"Agents en erreur : {names}."

        fallback_used = any(
            r.endpoint_used == LLMRouter.FALLBACK_MODEL
            for r in results
            if r.error is None
        )

        return DiagnosticResponse(
            diagnoses=list(diagnoses),
            confidence_score=confidence,
            agent_results=results,
            fallback_used=fallback_used,
            degraded_warning=degraded_warning,
        )

    # ------------------------------------------------------------------
    # Audit logging helper (Req 10.5)
    # ------------------------------------------------------------------

    async def _log_agent_invocation(self, result: AgentResult) -> None:
        """Log agent invocation to AuditLogger (best-effort)."""
        if self._audit_logger is None:
            return
        try:
            query_hash = hashlib.sha256(
                result.sub_question.encode()
            ).hexdigest()[:16]

            await self._audit_logger.log_action(
                user_id="system",
                action="agent_invocation",
                resource="agent_pipeline",
                resource_id=result.agent_name,
                details={
                    "agent": result.agent_name,
                    "query_hash": query_hash,
                    "endpoint": result.endpoint_used,
                    "duration_seconds": round(result.duration_seconds, 3),
                    "confidence_score": result.confidence_score,
                    "error": result.error,
                },
            )
        except Exception:
            logger.warning(
                "Failed to log agent invocation for %r", result.agent_name,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Partial-differential extraction (ported from _base_agent.py)
# ---------------------------------------------------------------------------

import json  # noqa: E402
import re  # noqa: E402

_CONDITION_RE = re.compile(
    r"(?:diagnostic|pathologie|condition|maladie)\s*[:\-–]\s*([^\n,;]+)",
    re.IGNORECASE,
)
_ICD_RE = re.compile(r"\b([A-Z]\d{2}(?:\.\d+)?)\b")


def _parse_partial_differential(answer: str) -> list[DifferentialDiagnosis]:
    """Extract a partial differential list from the LLM answer text.

    Returns a list of :class:`DifferentialDiagnosis` instances.
    Tries JSON extraction first; falls back to French-keyword regex.
    Falls back to an empty list when nothing can be parsed.
    """
    # 1. Try JSON extraction first
    json_match = re.search(r"\[.*\]", answer, re.DOTALL)
    if json_match:
        try:
            raw = json.loads(json_match.group())
            results = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                prob = max(0.0, min(1.0, float(item.get("probability", 0.5))))
                results.append(DifferentialDiagnosis(
                    condition=item.get("condition", "Unknown"),
                    probability=prob,
                    icd_code=item.get("icd_code"),
                    matching_symptoms=item.get("matching_symptoms", []),
                ))
            if results:
                return results
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # 2. Fallback to French-keyword regex
    results = []
    for match in _CONDITION_RE.finditer(answer):
        condition = match.group(1).strip().rstrip(".")
        icd_match = _ICD_RE.search(answer[match.start():match.start() + 120])
        results.append(DifferentialDiagnosis(
            condition=condition, probability=0.5,
            icd_code=icd_match.group(1) if icd_match else None,
            matching_symptoms=[],
        ))
    return results
