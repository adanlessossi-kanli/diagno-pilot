"""PromptBuilder — constructs LLM prompts for differential diagnosis."""
from __future__ import annotations

from backend.models.consultation import Symptom
from backend.models.patient import PatientProfile

# Mapping from locale prefix to (language label, guideline reference)
_LOCALE_LANGUAGE: dict[str, str] = {
    "fr-TG": "French",
    "fr-BJ": "French",
    "fr":    "French",
    "en":    "English",
}

_LOCALE_GUIDELINES: dict[str, str] = {
    "fr-TG": "CHU Lomé (TG)",
    "fr-BJ": "CHU Abomey-Calavi (BJ)",
    "fr":    "CHU Lomé (TG)",
    "en":    "OMS AFRO / MSF",
}


class PromptBuilder:
    """Stateless prompt constructor for the differential diagnosis pipeline.

    Sole responsibility: transform a list of symptoms and an optional patient
    profile into a plain-text prompt string ready to be sent to the LLM via
    RAGService.  The class performs no I/O, no HTTP calls, and no database
    access — it is a pure function wrapped in a class.

    Prompt structure produced by :meth:`build`:

    0. ``## Language and guidelines`` system instruction block (locale/region).
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
        locale: str = "fr-TG",
        region: str | None = None,
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
            locale: BCP-47 locale string (``fr-TG``, ``fr-BJ``, or ``en``).
                Defaults to ``fr-TG``.
            region: ISO 3166-1 alpha-2 country code (``TG``, ``BJ``) or
                ``None``.  When ``None``, the region line shows ``(none)``.

        Returns:
            A plain-text prompt string.  The same arguments always produce the
            same string (pure / deterministic).
        """
        lines: list[str] = []

        # ------------------------------------------------------------------
        # System instruction block: language and guidelines
        # ------------------------------------------------------------------
        language = _LOCALE_LANGUAGE.get(locale, "French")
        guidelines = _LOCALE_GUIDELINES.get(locale, "CHU Lomé (TG)")
        region_label = region if region else "(aucune)" if locale.startswith("fr") else "(none)"
        is_fr = locale.startswith("fr")

        lines.append("## Langue et directives" if is_fr else "## Language and guidelines")
        lines.append(f"- {'Répondre en' if is_fr else 'Respond in'}: {language}")
        lines.append(f"- {'Directives prioritaires' if is_fr else 'Prioritise guidelines from'}: {guidelines}")
        lines.append(f"- {'Région' if is_fr else 'Region'}: {region_label}")
        lines.append("")

        if patient_profile is not None:
            lines.append("## Profil patient" if is_fr else "## Patient profile")
            if patient_profile.age_group:
                age_label = "Groupe d'âge" if is_fr else "Age group"
                lines.append(f"- {age_label}: {patient_profile.age_group.value}")
            if patient_profile.weight_kg is not None:
                lines.append(f"- {'Poids' if is_fr else 'Weight'}: {patient_profile.weight_kg} kg")
            if patient_profile.comorbidities:
                comorbidities: list[str] = []
                if patient_profile.comorbidities.renal_failure:
                    comorbidities.append("insuffisance rénale" if is_fr else "renal failure")
                if patient_profile.comorbidities.hepatic_failure:
                    comorbidities.append("insuffisance hépatique" if is_fr else "hepatic failure")
                if comorbidities:
                    lines.append(f"- {'Comorbidités' if is_fr else 'Comorbidities'}: {', '.join(comorbidities)}")
            if patient_profile.allergies:
                lines.append(f"- {'Allergies connues' if is_fr else 'Known allergies'}: {', '.join(patient_profile.allergies)}")
            lines.append("")

        lines.append("## Symptômes" if is_fr else "## Symptoms")
        for s in symptoms:
            parts = [s.name]
            if s.severity:
                parts.append(f"severity={s.severity}")
            if s.duration_days is not None:
                parts.append(f"duration={s.duration_days}d")
            lines.append(f"- {', '.join(parts)}")

        lines.append("")
        if locale.startswith("fr"):
            lines.append(
                "En vous basant sur le profil patient et les symptômes ci-dessus, fournissez un "
                "diagnostic différentiel. Retournez AU MOINS 3 diagnostics sous forme de tableau JSON :\n"
                "[\n"
                '  {"condition": "<nom>", "probability": <0.0-1.0>, "icd_code": "<CIM-10>", '
                '"matching_symptoms": ["<symptôme>"]},\n'
                "  ...\n"
                "]\n"
                "Ordonnez par probabilité décroissante. Incluez uniquement le tableau JSON."
            )
        else:
            lines.append(
                "Based on the patient profile and symptoms above, provide a differential diagnosis. "
                "Return AT LEAST 3 diagnoses as a JSON array with the following structure:\n"
                "[\n"
                '  {"condition": "<diagnosis name>", "probability": <0.0-1.0>, "icd_code": "<ICD-10 code>", '
                '"matching_symptoms": ["<symptom>"]},\n'
                "  ...\n"
                "]\n"
                "Order by descending probability. Include only the JSON array in your response."
            )

        return "\n".join(lines)
