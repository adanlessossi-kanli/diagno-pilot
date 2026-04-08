"""Shared helpers for MCP server sub-question construction.

Provides functions to build detailed symptom text (with severity/duration)
and patient context strings from the tool arguments, so that all four
specialist servers include patient profile and symptom detail in their
sub-questions (Req 22.8, 22.9).
"""

from __future__ import annotations

from typing import Any


def build_symptom_text(symptoms: list[dict[str, Any]]) -> str:
    """Build a detailed symptom string including severity and duration.

    Returns a comma-separated list like:
        ``fièvre (sévérité=élevée, durée=3j), céphalées (sévérité=?, durée=?j)``

    When severity or duration_days are absent / None the placeholder ``?`` is
    used so the retrieval query still mentions the fields.
    """
    parts: list[str] = []
    for s in symptoms:
        if not isinstance(s, dict) or "name" not in s:
            continue
        name = s["name"]
        severity = s.get("severity") or "?"
        duration = s.get("duration_days")
        duration_str = f"{duration}j" if duration is not None else "?j"
        parts.append(f"{name} (sévérité={severity}, durée={duration_str})")
    return ", ".join(parts) if parts else ""


def build_patient_context(patient_profile: dict[str, Any] | None) -> str:
    """Build a French-language patient context clause from the profile dict.

    Returns an empty string when *patient_profile* is ``None`` or empty,
    so callers can safely append it to the sub-question.
    """
    if not patient_profile:
        return ""

    parts: list[str] = []

    age_group = patient_profile.get("age_group")
    if age_group:
        # age_group may be an enum value string like "adult" or "child"
        parts.append(f"groupe d'âge: {age_group}")

    weight = patient_profile.get("weight_kg")
    if weight is not None:
        parts.append(f"poids: {weight} kg")

    allergies = patient_profile.get("allergies")
    if allergies:
        parts.append(f"allergies: {', '.join(str(a) for a in allergies)}")

    comorbidities = patient_profile.get("comorbidities")
    if comorbidities and isinstance(comorbidities, dict):
        comorbidity_names: list[str] = []
        if comorbidities.get("renal_failure"):
            comorbidity_names.append("insuffisance rénale")
        if comorbidities.get("hepatic_failure"):
            comorbidity_names.append("insuffisance hépatique")
        if comorbidity_names:
            parts.append(f"comorbidités: {', '.join(comorbidity_names)}")

    if not parts:
        return ""
    return f" Profil patient : {'; '.join(parts)}."
