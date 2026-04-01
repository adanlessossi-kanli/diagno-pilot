"""PromptBuilder — constructs LLM prompts for differential diagnosis."""
from __future__ import annotations

from backend.models.consultation import Symptom
from backend.models.patient import PatientProfile


class PromptBuilder:
    """Stateless prompt constructor for the differential diagnosis pipeline.

    Sole responsibility: transform a list of symptoms and an optional patient
    profile into a plain-text prompt string ready to be sent to the LLM via
    RAGService.  The class performs no I/O, no HTTP calls, and no database
    access — it is a pure function wrapped in a class.

    Prompt structure produced by :meth:`build`:

    1. Optional ``## Patient profile`` section (age group, weight,
       comorbidities, allergies) — omitted when *patient_profile* is ``None``.
    2. ``## Symptoms`` section listing each symptom with severity and duration.
    3. Instruction paragraph asking the LLM to return a JSON array of ≥ 3
       diagnoses ordered by descending probability.
    """

    def build(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None,
    ) -> str:
        """Build and return the LLM prompt string.

        Args:
            symptoms: List of :class:`~backend.models.consultation.Symptom`
                objects describing the patient's current complaints.
            patient_profile: Optional
                :class:`~backend.models.patient.PatientProfile`.  When
                provided, age group, weight, comorbidities, and allergies are
                included in the prompt.  When ``None``, the patient-profile
                section is omitted entirely.

        Returns:
            A plain-text prompt string.  The same arguments always produce the
            same string (pure / deterministic).
        """
        lines: list[str] = []

        if patient_profile is not None:
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
            "[\n"
            '  {"condition": "<diagnosis name>", "probability": <0.0-1.0>, "icd_code": "<ICD-10 code>"},\n'
            "  ...\n"
            "]\n"
            "Order by descending probability. Include only the JSON array in your response."
        )

        return "\n".join(lines)
