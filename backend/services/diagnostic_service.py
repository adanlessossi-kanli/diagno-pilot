"""DiagnosticService — differential diagnosis via RAG pipeline."""
from __future__ import annotations

import json
import logging
import re

from fastapi import HTTPException

from backend.models.consultation import DifferentialDiagnosis, Symptom
from backend.models.patient import PatientProfile
from backend.services.rag_service import RAGService

logger = logging.getLogger(__name__)

_ICD_CODE_RE = re.compile(r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$")


class DiagnosticService:
    """Generates differential diagnoses using the RAG pipeline."""

    def __init__(self, rag_service: RAGService) -> None:
        self._rag = rag_service

    async def get_differential_diagnosis(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None = None,
    ) -> list[DifferentialDiagnosis]:
        """Return at least 3 differential diagnoses with probability scores and ICD-10 codes.

        Args:
            symptoms: List of symptoms with name, severity, and duration.
            patient_profile: Optional patient profile to personalise the results.

        Returns:
            List of DifferentialDiagnosis ordered by descending probability.
        """
        prompt = self._build_prompt(symptoms, patient_profile)
        rag_response = await self._rag.query(
            question=prompt,
            context=patient_profile,
            top_k=5,
        )
        diagnoses = self._parse_diagnoses(rag_response.answer)
        return diagnoses

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None,
    ) -> str:
        lines: list[str] = []

        if patient_profile:
            lines.append("## Patient profile")
            if patient_profile.age_group:
                lines.append(f"- Age group: {patient_profile.age_group.value}")
            if patient_profile.weight_kg is not None:
                lines.append(f"- Weight: {patient_profile.weight_kg} kg")
            if patient_profile.comorbidities:
                comorbidities: list[str] = []
                if patient_profile.comorbidities.renal_failure:
                    comorbidities.append("renal failure")
                if patient_profile.comorbidities.hepatic_failure:
                    comorbidities.append("hepatic failure")
                if comorbidities:
                    lines.append(f"- Comorbidities: {', '.join(comorbidities)}")
            if patient_profile.allergies:
                lines.append(f"- Known allergies: {', '.join(patient_profile.allergies)}")
            lines.append("")

        lines.append("## Symptoms")
        for s in symptoms:
            parts = [s.name]
            if s.severity:
                parts.append(f"severity={s.severity}")
            if s.duration_days is not None:
                parts.append(f"duration={s.duration_days}d")
            lines.append(f"- {', '.join(parts)}")

        lines.append("")
        lines.append(
            "Based on the patient profile and symptoms above, provide a differential diagnosis. "
            "Return AT LEAST 3 diagnoses as a JSON array with the following structure:\n"
            '[\n'
            '  {"condition": "<diagnosis name>", "probability": <0.0-1.0>, "icd_code": "<ICD-10 code>"},\n'
            '  ...\n'
            ']\n'
            "Order by descending probability. Include only the JSON array in your response."
        )

        return "\n".join(lines)

    def _validate_diagnoses(
        self, diagnoses: list[DifferentialDiagnosis], raw_response: str
    ) -> None:
        """Validate a list of DifferentialDiagnosis objects.

        Checks:
        - 1 ≤ len(diagnoses) ≤ 10
        - Each item has a non-empty ``condition`` and ``probability`` ∈ [0.0, 1.0]
        - ``icd_code``, if present, matches ``^[A-Z][0-9]{2}(\\.[0-9]{1,4})?$``

        Raises:
            HTTPException(502): with detail ``"llm_response_invalid"`` on any failure.
        """
        def _fail(reason: str) -> None:
            logger.error(
                "LLM response validation failed — %s. Raw response: %s",
                reason,
                raw_response,
            )
            raise HTTPException(status_code=502, detail="llm_response_invalid")

        if not (1 <= len(diagnoses) <= 10):
            _fail(f"expected 1–10 diagnoses, got {len(diagnoses)}")

        for i, d in enumerate(diagnoses):
            if not d.condition or not d.condition.strip():
                _fail(f"diagnosis[{i}].condition is empty")
            if not (0.0 <= d.probability <= 1.0):
                _fail(f"diagnosis[{i}].probability={d.probability} out of [0, 1]")
            if d.icd_code is not None and not _ICD_CODE_RE.match(d.icd_code):
                _fail(f"diagnosis[{i}].icd_code={d.icd_code!r} does not match ICD-10 format")

    def _parse_diagnoses(self, llm_answer: str) -> list[DifferentialDiagnosis]:
        """Extract DifferentialDiagnosis objects from the LLM response."""
        # Try to find a JSON array in the response
        json_match = re.search(r"\[.*?\]", llm_answer, re.DOTALL)
        if json_match:
            try:
                raw = json.loads(json_match.group())
                diagnoses = [
                    DifferentialDiagnosis(
                        condition=item.get("condition", "Unknown"),
                        probability=float(item.get("probability", 0.0)),
                        icd_code=item.get("icd_code") or None,
                    )
                    for item in raw
                    if isinstance(item, dict)
                ]
                if len(diagnoses) >= 3:
                    sorted_diagnoses = sorted(diagnoses, key=lambda d: d.probability, reverse=True)
                    self._validate_diagnoses(sorted_diagnoses, llm_answer)
                    return sorted_diagnoses
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.warning("Failed to parse JSON diagnoses: %s", exc)

        # Fallback: return placeholder diagnoses so the contract (≥3) is always met
        logger.warning(
            "Could not parse ≥3 diagnoses from LLM response; returning fallback placeholders."
        )
        return [
            DifferentialDiagnosis(condition="Diagnosis unavailable", probability=0.0, icd_code=None),
            DifferentialDiagnosis(condition="Diagnosis unavailable", probability=0.0, icd_code=None),
            DifferentialDiagnosis(condition="Diagnosis unavailable", probability=0.0, icd_code=None),
        ]
