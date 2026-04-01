"""DiagnosticOrchestrator — thin orchestrator for the differential diagnosis pipeline."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.models.consultation import DifferentialDiagnosis, Symptom
from backend.models.patient import PatientProfile
from backend.services.diagnostic_parser import DiagnosticParser
from backend.services.prompt_builder import PromptBuilder
from backend.services.rag_service import RAGService

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticResult:
    """Return value of DiagnosticOrchestrator.get_differential_diagnosis."""
    diagnoses: list[DifferentialDiagnosis]
    fallback_used: bool
    degraded_warning: str | None


class DiagnosticOrchestrator:
    """Thin orchestrator that coordinates PromptBuilder, RAGService, and DiagnosticParser
    to produce differential diagnoses.

    Orchestration flow:
    1. PromptBuilder.build() — constructs the LLM prompt from symptoms and patient profile.
    2. RAGService.query() — performs vector retrieval and LLM generation.
    3. DiagnosticParser.parse() — parses and validates the LLM JSON response.

    Collaborators:
    - :class:`~backend.services.prompt_builder.PromptBuilder`: pure prompt construction.
    - :class:`~backend.services.rag_service.RAGService`: retrieval-augmented generation.
    - :class:`~backend.services.diagnostic_parser.DiagnosticParser`: fault-tolerant response parsing.
    """

    def __init__(
        self,
        rag_service: RAGService,
        prompt_builder: PromptBuilder | None = None,
        diagnostic_parser: DiagnosticParser | None = None,
    ) -> None:
        self._rag = rag_service
        self._prompt_builder = prompt_builder if prompt_builder is not None else PromptBuilder()
        self._diagnostic_parser = diagnostic_parser if diagnostic_parser is not None else DiagnosticParser()

    async def get_differential_diagnosis(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None = None,
    ) -> DiagnosticResult:
        """Return at least 3 differential diagnoses for the given symptoms.

        End-to-end flow:
        1. Delegates prompt construction to ``self._prompt_builder.build()``.
        2. Delegates retrieval and generation to ``await self._rag.query()``.
        3. Delegates response parsing to ``self._diagnostic_parser.parse()``.

        The minimum of 3 diagnoses is guaranteed by DiagnosticParser: when the
        LLM response contains fewer than 3 parseable entries (or is malformed),
        DiagnosticParser returns 3 placeholder DifferentialDiagnosis objects
        with ``probability=0.0`` and ``icd_code=None``.

        Args:
            symptoms: List of symptoms with name, severity, and duration.
            patient_profile: Optional patient profile to personalise the results.

        Returns:
            DiagnosticResult with diagnoses, fallback_used, and degraded_warning
            propagated unchanged from RAGService.

        Raises:
            HTTPException: Propagated from RAGService if the LLM is unavailable.
        """
        prompt = self._prompt_builder.build(symptoms, patient_profile)
        rag_response = await self._rag.query(
            question=prompt,
            context=patient_profile,
            top_k=5,
        )
        diagnoses = self._diagnostic_parser.parse(rag_response.answer)
        return DiagnosticResult(
            diagnoses=diagnoses,
            fallback_used=rag_response.fallback_used,
            degraded_warning=rag_response.degraded_warning,
        )


# Backward-compatibility alias — all existing import sites continue to work.
DiagnosticService = DiagnosticOrchestrator
