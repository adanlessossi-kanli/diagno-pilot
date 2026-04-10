"""DiagnosticOrchestrator — thin orchestrator for the differential diagnosis pipeline."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.models.consultation import DifferentialDiagnosis, Symptom
from backend.models.patient import PatientProfile
from backend.core.config import settings
from backend.services.diagnostic_parser import DiagnosticParser
from backend.services.llamaindex_pipeline import LlamaIndexPipeline
from backend.services.prompt_builder import PromptBuilder

if TYPE_CHECKING:
    from backend.agents.synthesis_agent import Synthesis_Agent
    from backend.services.agent_pipeline import AgentPipeline
    from backend.services.audit_service import AuditLogger
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

_DIAGNOSIS_SYSTEM_PROMPT_FR = (
    "Tu es un assistant médical expert en maladies tropicales d'Afrique de l'Ouest "
    "(paludisme, fièvre typhoïde, dengue, méningite, schistosomiase, etc.). "
    "En te basant en priorité sur les passages de documents fournis, "
    "génère un diagnostic différentiel au format JSON strict. "
    "Si les passages ne contiennent pas assez d'information, utilise tes connaissances "
    "médicales pour compléter le diagnostic, en priorisant les pathologies endémiques "
    "de la région du patient (Togo, Bénin, Afrique de l'Ouest). "
    "Réponds UNIQUEMENT avec un tableau JSON valide, sans bloc de code markdown, "
    "sans texte avant ou après. "
    "IMPORTANT : Tous les noms de conditions dans le JSON DOIVENT être en FRANÇAIS, "
    "suivis du nom anglais entre parenthèses. Les symptômes doivent être en FRANÇAIS uniquement. "
    "Format requis : "
    '[{"condition": "<nom en français> (<English name>)", "probability": <0.0-1.0>, "icd_code": "<CIM-10>", '
    '"matching_symptoms": ["<symptôme en français>"]}, ...]. '
    "Exemple de condition : \"Myélite flasque aiguë (Acute Flaccid Myelitis)\". "
    "Inclure au moins 3 diagnostics ordonnés par probabilité décroissante."
)

_DIAGNOSIS_SYSTEM_PROMPT_EN = (
    "You are a medical assistant specializing in West African tropical diseases "
    "(malaria, typhoid fever, dengue, meningitis, schistosomiasis, etc.). "
    "Based primarily on the provided document passages, generate a differential diagnosis "
    "in strict JSON format. If the passages lack sufficient information, use your medical "
    "knowledge to complete the diagnosis, prioritizing endemic pathologies of the patient's "
    "region (Togo, Benin, West Africa). "
    "Respond ONLY with a valid JSON array, no markdown code blocks, no text before or after. "
    "ALL condition names in the JSON MUST be in ENGLISH, "
    "followed by the local-language name in parentheses when the user locale is not English. "
    "Symptoms must be in ENGLISH. "
    "Required format: "
    '[{"condition": "<name in English>", "probability": <0.0-1.0>, "icd_code": "<ICD-10>", '
    '"matching_symptoms": ["<symptom in English>"]}, ...]. '
    "Include at least 3 diagnoses ordered by descending probability."
)


def _get_diagnosis_system_prompt(locale: str) -> str:
    """Return the diagnosis system prompt in the appropriate language."""
    if locale.startswith("fr"):
        return _DIAGNOSIS_SYSTEM_PROMPT_FR
    return _DIAGNOSIS_SYSTEM_PROMPT_EN


# Keep backward-compat alias for any code referencing the old constant
DIAGNOSIS_SYSTEM_PROMPT = _DIAGNOSIS_SYSTEM_PROMPT_FR


@dataclass
class DiagnosticResult:
    """Return value of DiagnosticOrchestrator.get_differential_diagnosis."""
    diagnoses: list[DifferentialDiagnosis]
    fallback_used: bool
    degraded_warning: str | None
    locale: str = "fr-TG"
    language_mismatch: bool = False
    disclaimer: str | None = None
    session_id: str | None = None
    confidence_score: float = 0.0
    evidence_citations: list = field(default_factory=list)
    agent_contributions: list = field(default_factory=list)
    parse_failed: bool = False
    consultation_persisted: bool = False


class DiagnosticOrchestrator:
    """Thin orchestrator that coordinates PromptBuilder, LlamaIndexPipeline, and DiagnosticParser
    to produce differential diagnoses.

    When ``mcp_host`` is provided, delegates to ``MCP_Host.run_diagnostic()`` and
    ``Synthesis_Agent.synthesize()`` instead of the LlamaIndex path (REQ 2.8).
    The existing LlamaIndex path is preserved when ``mcp_host`` is ``None``.

    Orchestration flow (LlamaIndex path):
    1. PromptBuilder.build() — constructs the LLM prompt from symptoms and patient profile.
    2. LlamaIndexPipeline.query() — performs vector retrieval and LLM generation.
    3. DiagnosticParser.parse() — parses and validates the LLM JSON response.

    Orchestration flow (MCP path):
    1. MCP_Host.run_diagnostic() — runs four specialist agents in parallel.
    2. Synthesis_Agent.synthesize() — merges agent results into a DiagnosticResult.

    Collaborators:
    - :class:`~backend.services.prompt_builder.PromptBuilder`: pure prompt construction.
    - :class:`~backend.services.llamaindex_pipeline.LlamaIndexPipeline`: retrieval-augmented generation.
    - :class:`~backend.services.diagnostic_parser.DiagnosticParser`: fault-tolerant response parsing.
    - :class:`~backend.services.mcp_host.MCP_Host`: optional multi-agent orchestrator.
    - :class:`~backend.agents.synthesis_agent.Synthesis_Agent`: optional result merger.
    """

    def __init__(
        self,
        rag_service: LlamaIndexPipeline,
        prompt_builder: PromptBuilder | None = None,
        diagnostic_parser: DiagnosticParser | None = None,
        mcp_host: "MCP_Host | None" = None,
        synthesis_agent: "Synthesis_Agent | None" = None,
        db: AsyncIOMotorDatabase | None = None,
        agent_pipeline: "AgentPipeline | None" = None,
        audit_logger: "AuditLogger | None" = None,
    ) -> None:
        self._rag = rag_service
        self._prompt_builder = prompt_builder if prompt_builder is not None else PromptBuilder()
        self._diagnostic_parser = diagnostic_parser if diagnostic_parser is not None else DiagnosticParser()
        self._mcp_host = mcp_host
        self._db = db
        self._agent_pipeline = agent_pipeline
        self._audit_logger = audit_logger
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
        user_id: str | None = None,
    ) -> DiagnosticResult:
        """Return at least 3 differential diagnoses for the given symptoms.

        When ``self._mcp_host`` is set, delegates to the MCP multi-agent path
        (REQ 2.8). Otherwise uses the existing LlamaIndex path unchanged.

        After each call (both paths), a DiagnosticAudit document is written to
        MongoDB (REQ 4.3). When fallback_used=True, a disclaimer is added to
        the result (REQ 4.2).

        Args:
            symptoms: List of symptoms with name, severity, and duration.
            patient_profile: Optional patient profile to personalise the results.
            locale: BCP-47 locale string (e.g. ``fr-TG``, ``fr-BJ``, ``en``).
                Defaults to ``fr-TG``.
            region: ISO 3166-1 alpha-2 country code or ``None``.
            user_id: Optional authenticated user ID for consultation creation.

        Returns:
            DiagnosticResult with diagnoses, fallback_used, degraded_warning,
            locale, language_mismatch, and disclaimer fields.

        Raises:
            HTTPException: Propagated from RAGService if the LLM is unavailable.
        """
        # Route to the appropriate diagnosis path based on DIAGNOSIS_MODE.
        mode = settings.DIAGNOSIS_MODE

        if mode == "mcp":
            if self._mcp_host is None:
                logger.warning("DIAGNOSIS_MODE=mcp but MCP_Host not configured; falling back to RAG")
                result = await self._get_diagnosis_via_rag(symptoms, patient_profile, locale, region)
            else:
                result = await self._get_diagnosis_via_mcp(symptoms, patient_profile, locale, region, user_id=user_id)
        elif mode == "agent":
            if self._agent_pipeline is None:
                logger.warning("DIAGNOSIS_MODE=agent but AgentPipeline not configured; falling back to RAG")
                result = await self._get_diagnosis_via_rag(symptoms, patient_profile, locale, region)
            else:
                result = await self._get_diagnosis_via_agent_pipeline(symptoms, patient_profile, locale, region)
        else:  # "rag" (default)
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
                confidence_score=result.confidence_score,
                diagnoses=[d.model_dump() for d in result.diagnoses],
                fallback_used=result.fallback_used,
                degraded_warning=result.degraded_warning,
                agent_results=[
                    c if isinstance(c, dict) else (c.model_dump() if hasattr(c, "model_dump") else vars(c))
                    for c in result.agent_contributions
                ] if result.agent_contributions else [],
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
        *,
        user_id: str | None = None,
    ) -> DiagnosticResult:
        """MCP multi-agent path — REQ 2.8, 6.1, 6.3, 7.1, 11.1, 15.4."""
        assert self._mcp_host is not None  # guarded by caller
        assert self._synthesis_agent is not None  # always set when mcp_host is set

        mcp_session_id = str(uuid.uuid4())
        start = time.perf_counter()

        agent_results, audit_data = await self._mcp_host.run_diagnostic(
            symptoms=symptoms,
            patient_profile=patient_profile,
            locale=locale,
            region=region,
        )

        result = self._synthesis_agent.synthesize(agent_results, locale=locale)

        # If agents returned chunks but no differentials (retrieval-only mode),
        # use the LLM to generate diagnoses from the merged chunks.
        all_chunks_content = []
        for ar in agent_results:
            for chunk in ar.chunks:
                excerpt = chunk.get("excerpt", chunk.get("content", ""))
                if excerpt:
                    all_chunks_content.append(excerpt[:300])

        has_only_placeholders = all(
            d.condition.startswith("Diagnostic différentiel") for d in result.diagnoses
        )

        if has_only_placeholders and all_chunks_content:
            try:
                context_text = "\n---\n".join(all_chunks_content[:5])
                symptom_names = ", ".join(s.name for s in symptoms)
                llm_context = [
                    {"role": "system", "content": _get_diagnosis_system_prompt(locale)},
                    {"role": "system", "content": f"Documents pertinents :\n{context_text}"},
                ]
                llm_result = await self._rag._llm.generate(
                    f"Symptômes : {symptom_names}", llm_context
                )
                parsed, _parse_failed = self._diagnostic_parser.parse(llm_result.answer, locale=locale)
                if parsed and len(parsed) >= 3:
                    result.diagnoses = parsed
                    result.fallback_used = llm_result.fallback_used
            except Exception as exc:
                logger.warning("LLM diagnosis generation failed: %s", exc)

        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        logger.info(
            "MCP session %s completed in %.1f ms — timeouts=%r omissions=%r agents=%d diagnoses=%d",
            mcp_session_id,
            duration_ms,
            audit_data.timeouts,
            audit_data.omissions,
            len(audit_data.agent_results),
            len(result.diagnoses),
        )

        # Handle fallback_used from AgentResults — REQ 6.2, 8.3
        if result.fallback_used:
            result.disclaimer = FALLBACK_DISCLAIMER

        # Assign session_id — REQ 6.3
        result.session_id = mcp_session_id

        # Auto-create Consultation — REQ 11.1, 11.11 (best-effort)
        await self._create_mcp_consultation(
            mcp_session_id=mcp_session_id,
            user_id=user_id,
            symptoms=symptoms,
            result=result,
        )

        return result

    async def _create_mcp_consultation(
        self,
        *,
        mcp_session_id: str,
        user_id: str | None,
        symptoms: list[Symptom],
        result: DiagnosticResult,
        patient_id: str | None = None,
    ) -> None:
        """Auto-create a Consultation document for the MCP session — REQ 11.1–11.8, 11.11.

        Best-effort: catches all exceptions and logs errors so the diagnostic
        response is never blocked by a consultation write failure.
        Skips creation when ``user_id`` is ``None`` (internal/test calls).
        """
        if user_id is None:
            logger.debug("_create_mcp_consultation: no user_id, skipping")
            return
        if self._db is None:
            logger.debug("_create_mcp_consultation: no db configured, skipping")
            return
        try:
            from backend.models.consultation import (
                AgentContribution,
                Consultation,
                EvidenceCitation,
            )

            consultation = Consultation(
                patient_id=patient_id,
                user_id=user_id,
                symptoms=symptoms,
                diagnoses=result.diagnoses,
                is_one_shot=patient_id is None,
                created_at=datetime.now(timezone.utc),
                mcp_session_id=mcp_session_id,
                agent_contributions=[
                    AgentContribution(**c) if isinstance(c, dict) else c
                    for c in result.agent_contributions
                ],
                evidence_citations=[
                    EvidenceCitation(**c) if isinstance(c, dict) else c
                    for c in result.evidence_citations
                ],
            )
            await self._db["consultations"].insert_one(consultation.model_dump())
            result.consultation_persisted = True
            logger.debug(
                "MCP Consultation created for session %s user_id=%s",
                mcp_session_id,
                user_id,
            )
        except Exception as exc:
            logger.error("Failed to create MCP Consultation: %s", exc)

    async def _get_diagnosis_via_agent_pipeline(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None,
        locale: str,
        region: str | None,
    ) -> DiagnosticResult:
        """AgentPipeline path — in-process LlamaIndex multi-agent pipeline (Req 10.1)."""
        assert self._agent_pipeline is not None

        symptom_dicts = [s.model_dump() for s in symptoms]
        pipeline_response = await self._agent_pipeline.run(
            symptoms=symptom_dicts,
            patient_profile=patient_profile,
            region=region,
        )

        # Log diagnostic session to HIPAA AuditLogger (Req 10.5)
        if self._audit_logger is not None:
            try:
                await self._audit_logger.log_action(
                    user_id="system",
                    action="diagnostic_session",
                    resource="agent_pipeline",
                    details={
                        "locale": locale,
                        "region": region,
                        "agent_count": len(pipeline_response.agent_results),
                        "diagnosis_count": len(pipeline_response.diagnoses),
                        "fallback_used": pipeline_response.fallback_used,
                    },
                )
            except Exception:
                logger.warning("Failed to log diagnostic session to AuditLogger")

        result = DiagnosticResult(
            diagnoses=pipeline_response.diagnoses,
            fallback_used=pipeline_response.fallback_used,
            degraded_warning=pipeline_response.degraded_warning,
            locale=locale,
        )

        logger.info(
            "DiagnosticAudit [AgentPipeline path] — fallback_used=%r degraded_warning=%r diagnoses=%d",
            result.fallback_used,
            result.degraded_warning,
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
        """Original LlamaIndex path — preserved unchanged."""
        prompt = self._prompt_builder.build(symptoms, patient_profile, locale=locale, region=region)
        rag_response = await self._rag.query(
            question=prompt,
            context=patient_profile,
            top_k=5,
            region=region,
            system_prompt=_get_diagnosis_system_prompt(locale),
        )
        diagnoses, parse_failed = self._diagnostic_parser.parse(rag_response.answer, locale=locale)

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
            parse_failed=parse_failed,
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
