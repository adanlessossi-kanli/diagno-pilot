"""DiagnosticOrchestrator — thin orchestrator for the differential diagnosis pipeline."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.models.consultation import DifferentialDiagnosis, Symptom
from backend.models.patient import PatientProfile
from backend.services.diagnostic_parser import DiagnosticParser
from backend.services.prompt_builder import PromptBuilder
from backend.services.rag_service import RAGService

if TYPE_CHECKING:
    from backend.agents.synthesis_agent import Synthesis_Agent
    from backend.services.mcp_host import MCP_Host

try:
    import langdetect
except ImportError:
    langdetect = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_LOCALE_LANG_MAP: dict[str, str] = {
    "fr-TG": "fr",
    "fr-BJ": "fr",
    "fr": "fr",
    "en": "en",
}

FALLBACK_DISCLAIMER = (
    "⚠️ Cette réponse a été générée par le modèle de secours et nécessite une vérification clinique."
)


@dataclass
class DiagnosticResult:
    """Return value of DiagnosticOrchestrator.get_differential_diagnosis."""
    diagnoses: list[DifferentialDiagnosis]
    fallback_used: bool
    degraded_warning: str | None
    locale: str = "fr-TG"
    language_mismatch: bool = False
    disclaimer: str | None = None


class DiagnosticOrchestrator:
    """Thin orchestrator that coordinates PromptBuilder, RAGService, and DiagnosticParser
    to produce differential diagnoses.

    When ``mcp_host`` is provided, delegates to ``MCP_Host.run_diagnostic()`` and
    ``Synthesis_Agent.synthesize()`` instead of the RAGService path (REQ 2.8).
    The existing RAGService path is preserved when ``mcp_host`` is ``None``.

    Orchestration flow (RAGService path):
    1. PromptBuilder.build() — constructs the LLM prompt from symptoms and patient profile.
    2. RAGService.query() — performs vector retrieval and LLM generation.
    3. DiagnosticParser.parse() — parses and validates the LLM JSON response.

    Orchestration flow (MCP path):
    1. MCP_Host.run_diagnostic() — runs four specialist agents in parallel.
    2. Synthesis_Agent.synthesize() — merges agent results into a DiagnosticResult.

    Collaborators:
    - :class:`~backend.services.prompt_builder.PromptBuilder`: pure prompt construction.
    - :class:`~backend.services.rag_service.RAGService`: retrieval-augmented generation.
    - :class:`~backend.services.diagnostic_parser.DiagnosticParser`: fault-tolerant response parsing.
    - :class:`~backend.services.mcp_host.MCP_Host`: optional multi-agent orchestrator.
    - :class:`~backend.agents.synthesis_agent.Synthesis_Agent`: optional result merger.
    """

    def __init__(
        self,
        rag_service: RAGService,
        prompt_builder: PromptBuilder | None = None,
        diagnostic_parser: DiagnosticParser | None = None,
        mcp_host: "MCP_Host | None" = None,
        synthesis_agent: "Synthesis_Agent | None" = None,
        db: AsyncIOMotorDatabase | None = None,
    ) -> None:
        self._rag = rag_service
        self._prompt_builder = prompt_builder if prompt_builder is not None else PromptBuilder()
        self._diagnostic_parser = diagnostic_parser if diagnostic_parser is not None else DiagnosticParser()
        self._mcp_host = mcp_host
        self._db = db
        # Create a default Synthesis_Agent when mcp_host is provided but synthesis_agent is not.
        if mcp_host is not None and synthesis_agent is None:
            from backend.agents.synthesis_agent import Synthesis_Agent as _SynthesisAgent
            self._synthesis_agent: "Synthesis_Agent | None" = _SynthesisAgent()
        else:
            self._synthesis_agent = synthesis_agent

    async def get_differential_diagnosis(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None = None,
        locale: str = "fr-TG",
        region: str | None = None,
    ) -> DiagnosticResult:
        """Return at least 3 differential diagnoses for the given symptoms.

        When ``self._mcp_host`` is set, delegates to the MCP multi-agent path
        (REQ 2.8). Otherwise uses the existing RAGService path unchanged.

        After each call (both paths), a DiagnosticAudit document is written to
        MongoDB (REQ 4.3). When fallback_used=True, a disclaimer is added to
        the result (REQ 4.2).

        Args:
            symptoms: List of symptoms with name, severity, and duration.
            patient_profile: Optional patient profile to personalise the results.
            locale: BCP-47 locale string (e.g. ``fr-TG``, ``fr-BJ``, ``en``).
                Defaults to ``fr-TG``.
            region: ISO 3166-1 alpha-2 country code or ``None``.

        Returns:
            DiagnosticResult with diagnoses, fallback_used, degraded_warning,
            locale, language_mismatch, and disclaimer fields.

        Raises:
            HTTPException: Propagated from RAGService if the LLM is unavailable.
        """
        if self._mcp_host is not None:
            result = await self._get_diagnosis_via_mcp(symptoms, patient_profile, locale, region)
        else:
            result = await self._get_diagnosis_via_rag(symptoms, patient_profile, locale, region)

        # Add disclaimer when fallback LLM was used — REQ 4.2
        if result.fallback_used:
            result.disclaimer = FALLBACK_DISCLAIMER

        # Write DiagnosticAudit to MongoDB — REQ 4.3 (best-effort, never fails the call)
        await self._write_audit(symptoms, patient_profile, locale, region, result)

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_audit(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None,
        locale: str,
        region: str | None,
        result: DiagnosticResult,
    ) -> None:
        """Write a DiagnosticAudit document to MongoDB — REQ 4.3."""
        if self._db is None:
            logger.debug("DiagnosticOrchestrator: no db configured, skipping audit write")
            return
        try:
            from backend.models.diagnostic_audit import DiagnosticAudit

            # Compute patient profile hash (non-PII fields only) — REQ 4.3
            age = None
            weight = None
            sex = None
            comorbidities_dict = None
            if patient_profile is not None:
                weight = patient_profile.weight_kg
                comorbidities_dict = patient_profile.comorbidities.model_dump() if patient_profile.comorbidities else None

            patient_hash = DiagnosticAudit.compute_patient_hash(
                age=age,
                weight=weight,
                sex=sex,
                comorbidities=comorbidities_dict,
            )

            audit = DiagnosticAudit(
                timestamp=datetime.now(timezone.utc),
                symptoms=[s.model_dump() for s in symptoms],
                patient_profile_hash=patient_hash,
                locale=locale,
                region=region,
                confidence_score=0.0,  # RAG path doesn't expose per-call score here
                diagnoses=[d.model_dump() for d in result.diagnoses],
                fallback_used=result.fallback_used,
                degraded_warning=result.degraded_warning,
                agent_results=[],
            )

            await self._db["diagnostic_audit"].insert_one(audit.model_dump())
            logger.debug("DiagnosticAudit written for locale=%r region=%r", locale, region)
        except Exception as exc:
            logger.error("Failed to write DiagnosticAudit: %s", exc)

    async def _get_diagnosis_via_mcp(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None,
        locale: str,
        region: str | None,
    ) -> DiagnosticResult:
        """MCP multi-agent path — REQ 2.8."""
        assert self._mcp_host is not None  # guarded by caller
        assert self._synthesis_agent is not None  # always set when mcp_host is set

        agent_results, audit_data = await self._mcp_host.run_diagnostic(
            symptoms=symptoms,
            patient_profile=patient_profile,
            locale=locale,
            region=region,
        )

        result = self._synthesis_agent.synthesize(agent_results, locale=locale)

        logger.info(
            "DiagnosticAudit [MCP path] — timeouts=%r omissions=%r agents=%d diagnoses=%d",
            audit_data.timeouts,
            audit_data.omissions,
            len(audit_data.agent_results),
            len(result.diagnoses),
        )

        return result

    async def _get_diagnosis_via_rag(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None,
        locale: str,
        region: str | None,
    ) -> DiagnosticResult:
        """Original RAGService path — preserved unchanged."""
        prompt = self._prompt_builder.build(symptoms, patient_profile, locale=locale, region=region)
        rag_response = await self._rag.query(
            question=prompt,
            context=patient_profile,
            top_k=5,
            region=region,
        )
        diagnoses = self._diagnostic_parser.parse(rag_response.answer)

        # Language mismatch detection
        language_mismatch = False
        expected_lang = _LOCALE_LANG_MAP.get(locale, "fr")
        if langdetect is not None:
            try:
                detected_lang = langdetect.detect(rag_response.answer)
                if detected_lang != expected_lang:
                    language_mismatch = True
                    logger.warning(
                        "Language mismatch: requested locale=%r (expected lang=%r) but detected=%r",
                        locale, expected_lang, detected_lang,
                    )
            except Exception:
                pass  # langdetect failure is non-fatal

        result = DiagnosticResult(
            diagnoses=diagnoses,
            fallback_used=rag_response.fallback_used,
            degraded_warning=rag_response.degraded_warning,
            locale=locale,
            language_mismatch=language_mismatch,
        )

        logger.info(
            "DiagnosticAudit [RAG path] — fallback_used=%r degraded_warning=%r diagnoses=%d",
            result.fallback_used,
            result.degraded_warning,
            len(result.diagnoses),
        )

        return result


# Backward-compatibility alias — all existing import sites continue to work.
DiagnosticService = DiagnosticOrchestrator
