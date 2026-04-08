"""Tests for PromptBuilder i18n extensions — Task 8.

Covers:
- 8.2  Property 9: prompt contains locale and region instructions (Hypothesis)
- 8.3  Snapshot unit tests for each locale/region combination
"""
from __future__ import annotations

# Feature: i18n-medical-content, Property 9: prompt contains locale and region instructions

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.consultation import Symptom
from backend.services.prompt_builder import PromptBuilder

# ---------------------------------------------------------------------------
# Supported locale/region combinations
# ---------------------------------------------------------------------------

LOCALE_REGION_PAIRS: list[tuple[str, str | None]] = [
    ("fr-TG", "TG"),
    ("fr-TG", None),
    ("fr-BJ", "BJ"),
    ("fr-BJ", None),
    ("en", None),
    ("en", "TG"),
    ("en", "BJ"),
]

locale_region_st = st.sampled_from(LOCALE_REGION_PAIRS)


# ---------------------------------------------------------------------------
# 8.2  Property 9: prompt contains locale and region instructions
# **Validates: Requirements 4.1, 4.2, 4.3**
# ---------------------------------------------------------------------------

@given(locale_region=locale_region_st)
@h_settings(max_examples=100)
def test_property_9_prompt_contains_locale_and_region_instructions(
    locale_region: tuple[str, str | None],
) -> None:
    """Feature: i18n-medical-content, Property 9: prompt contains locale and region instructions.

    For any supported locale and region pair, the prompt string produced by
    PromptBuilder.build() SHALL contain a language instruction (French for
    fr-TG/fr-BJ, English for en) and a guideline reference (CHU Lomé for TG,
    CHU Abomey-Calavi for BJ, OMS AFRO/MSF for en).

    **Validates: Requirements 4.1, 4.2, 4.3**
    """
    locale, region = locale_region
    pb = PromptBuilder()
    prompt = pb.build([], None, locale=locale, region=region)

    # Language instruction must be present
    if locale in ("fr-TG", "fr-BJ", "fr"):
        assert "French" in prompt, (
            f"Expected 'French' in prompt for locale={locale!r}, got:\n{prompt}"
        )
    elif locale == "en":
        assert "English" in prompt, (
            f"Expected 'English' in prompt for locale={locale!r}, got:\n{prompt}"
        )

    # Guideline reference must be present
    if locale == "fr-TG" or locale == "fr":
        assert "CHU Lomé" in prompt, (
            f"Expected 'CHU Lomé' in prompt for locale={locale!r}, got:\n{prompt}"
        )
    elif locale == "fr-BJ":
        assert "CHU Abomey-Calavi" in prompt, (
            f"Expected 'CHU Abomey-Calavi' in prompt for locale={locale!r}, got:\n{prompt}"
        )
    elif locale == "en":
        assert "OMS AFRO" in prompt or "MSF" in prompt, (
            f"Expected 'OMS AFRO' or 'MSF' in prompt for locale={locale!r}, got:\n{prompt}"
        )

    # The system instruction block header must always be present
    assert "## Language and guidelines" in prompt or "## Langue et directives" in prompt, (
        f"Expected language/guidelines header in prompt, got:\n{prompt}"
    )


# ---------------------------------------------------------------------------
# 8.3  Snapshot unit tests for PromptBuilder locale/region combinations
# Requirements: 4.1, 4.2, 4.3
# ---------------------------------------------------------------------------

def test_fr_tg_region_tg_system_block() -> None:
    """fr-TG / region TG: French language, CHU Lomé."""
    pb = PromptBuilder()
    prompt = pb.build([], None, locale="fr-TG", region="TG")

    assert "## Langue et directives" in prompt
    assert "- Répondre en: French" in prompt
    assert "- Directives prioritaires: CHU Lomé (TG)" in prompt
    assert "- Région: TG" in prompt


def test_fr_bj_region_bj_system_block() -> None:
    """fr-BJ / region BJ: French language, CHU Abomey-Calavi."""
    pb = PromptBuilder()
    prompt = pb.build([], None, locale="fr-BJ", region="BJ")

    assert "## Langue et directives" in prompt
    assert "- Répondre en: French" in prompt
    assert "- Directives prioritaires: CHU Abomey-Calavi (BJ)" in prompt
    assert "- Région: BJ" in prompt


def test_en_no_region_system_block() -> None:
    """en / region None: English language, OMS AFRO / MSF."""
    pb = PromptBuilder()
    prompt = pb.build([], None, locale="en", region=None)

    assert "## Language and guidelines" in prompt
    assert "- Respond in: English" in prompt
    assert "- Prioritise guidelines from: OMS AFRO / MSF" in prompt
    assert "- Region: (none)" in prompt


def test_fr_alias_region_tg_behaves_like_fr_tg() -> None:
    """fr alias / region TG: should behave like fr-TG (French, CHU Lomé)."""
    pb = PromptBuilder()
    prompt = pb.build([], None, locale="fr", region="TG")

    assert "## Langue et directives" in prompt
    assert "- Répondre en: French" in prompt
    assert "- Directives prioritaires: CHU Lomé (TG)" in prompt
    assert "- Région: TG" in prompt


def test_system_block_appears_before_symptoms() -> None:
    """The language/guidelines block must appear before the symptoms section."""
    pb = PromptBuilder()
    prompt = pb.build([], None, locale="fr-TG", region="TG")

    lang_pos = prompt.index("## Langue et directives")
    symptoms_pos = prompt.index("## Symptômes")
    assert lang_pos < symptoms_pos, (
        "Language and guidelines block must precede the Symptoms section"
    )


def test_system_block_appears_before_patient_profile() -> None:
    """The language/guidelines block must appear before the patient profile section."""
    from backend.models.common import AgeGroup
    from backend.models.patient import Comorbidities, PatientProfile

    pb = PromptBuilder()
    profile = PatientProfile(
        full_name=None,
        date_of_birth=None,
        weight_kg=70.0,
        age_group=AgeGroup.ADULT,
        allergies=[],
        comorbidities=Comorbidities(renal_failure=False, hepatic_failure=False),
        current_medications=[],
    )
    prompt = pb.build([], profile, locale="fr-TG", region="TG")

    lang_pos = prompt.index("## Langue et directives")
    profile_pos = prompt.index("## Profil patient")
    assert lang_pos < profile_pos, (
        "Language and guidelines block must precede the Patient profile section"
    )


def test_default_locale_is_fr_tg() -> None:
    """Default locale (no args) should produce French / CHU Lomé block."""
    pb = PromptBuilder()
    prompt = pb.build([], None)

    assert "- Répondre en: French" in prompt
    assert "- Directives prioritaires: CHU Lomé (TG)" in prompt
    assert "- Région: (aucune)" in prompt


# ---------------------------------------------------------------------------
# Property 13: PromptBuilder locale-aware instruction language
# Feature: chat-diagnosis-improvements
# **Validates: Requirements 23.1, 23.2**
# ---------------------------------------------------------------------------

_locale_st = st.sampled_from(["fr-TG", "fr-BJ", "fr", "en"])

_symptom_st = st.builds(
    Symptom,
    name=st.text(min_size=1, max_size=50).filter(str.strip),
    severity=st.one_of(st.none(), st.sampled_from(["mild", "moderate", "severe"])),
    duration_days=st.one_of(st.none(), st.integers(min_value=0, max_value=365)),
)

_symptoms_list_st = st.lists(_symptom_st, min_size=0, max_size=5)


@given(locale=_locale_st, symptoms=_symptoms_list_st)
@h_settings(max_examples=100)
def test_property_13_locale_aware_instruction_language(
    locale: str, symptoms: list[Symptom],
) -> None:
    """Feature: chat-diagnosis-improvements, Property 13: PromptBuilder locale-aware instruction language.

    For any locale string, the instruction paragraph produced by
    PromptBuilder.build() SHALL be written in French when the locale starts
    with "fr" and in English otherwise. The JSON schema in the instruction
    SHALL include the matching_symptoms field.

    **Validates: Requirements 23.1, 23.2**
    """
    pb = PromptBuilder()
    prompt = pb.build(symptoms, None, locale=locale)

    # Req 23.1: French instruction for fr* locales, English otherwise
    if locale.startswith("fr"):
        assert "diagnostic différentiel" in prompt, (
            f"Expected French instruction for locale={locale!r}"
        )
        assert "AU MOINS 3" in prompt, (
            f"Expected French '≥3' instruction for locale={locale!r}"
        )
    else:
        assert "differential diagnosis" in prompt, (
            f"Expected English instruction for locale={locale!r}"
        )
        assert "AT LEAST 3" in prompt, (
            f"Expected English '≥3' instruction for locale={locale!r}"
        )

    # Req 23.2: JSON schema includes matching_symptoms
    assert "matching_symptoms" in prompt, (
        f"Expected 'matching_symptoms' in JSON schema for locale={locale!r}"
    )


def test_property_13_french_locale_uses_french_instruction() -> None:
    """French locales produce French instruction paragraph with matching_symptoms."""
    pb = PromptBuilder()
    for locale in ("fr-TG", "fr-BJ", "fr"):
        prompt = pb.build([], None, locale=locale)
        assert "diagnostic différentiel" in prompt
        assert "AU MOINS 3" in prompt
        assert "matching_symptoms" in prompt
        # Should NOT contain the English instruction
        assert "differential diagnosis" not in prompt


def test_property_13_english_locale_uses_english_instruction() -> None:
    """English locale produces English instruction paragraph with matching_symptoms."""
    pb = PromptBuilder()
    prompt = pb.build([], None, locale="en")
    assert "differential diagnosis" in prompt
    assert "AT LEAST 3" in prompt
    assert "matching_symptoms" in prompt
    # Should NOT contain the French instruction
    assert "diagnostic différentiel" not in prompt
