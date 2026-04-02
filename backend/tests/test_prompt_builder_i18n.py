"""Tests for PromptBuilder i18n extensions — Task 8.

Covers:
- 8.2  Property 9: prompt contains locale and region instructions (Hypothesis)
- 8.3  Snapshot unit tests for each locale/region combination
"""
from __future__ import annotations

# Feature: i18n-medical-content, Property 9: prompt contains locale and region instructions

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

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
    assert "## Language and guidelines" in prompt, (
        f"Expected '## Language and guidelines' header in prompt, got:\n{prompt}"
    )


# ---------------------------------------------------------------------------
# 8.3  Snapshot unit tests for PromptBuilder locale/region combinations
# Requirements: 4.1, 4.2, 4.3
# ---------------------------------------------------------------------------

def test_fr_tg_region_tg_system_block() -> None:
    """fr-TG / region TG: French language, CHU Lomé."""
    pb = PromptBuilder()
    prompt = pb.build([], None, locale="fr-TG", region="TG")

    assert "## Language and guidelines" in prompt
    assert "- Respond in: French" in prompt
    assert "- Prioritise guidelines from: CHU Lomé (TG)" in prompt
    assert "- Region: TG" in prompt


def test_fr_bj_region_bj_system_block() -> None:
    """fr-BJ / region BJ: French language, CHU Abomey-Calavi."""
    pb = PromptBuilder()
    prompt = pb.build([], None, locale="fr-BJ", region="BJ")

    assert "## Language and guidelines" in prompt
    assert "- Respond in: French" in prompt
    assert "- Prioritise guidelines from: CHU Abomey-Calavi (BJ)" in prompt
    assert "- Region: BJ" in prompt


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

    assert "## Language and guidelines" in prompt
    assert "- Respond in: French" in prompt
    assert "- Prioritise guidelines from: CHU Lomé (TG)" in prompt
    assert "- Region: TG" in prompt


def test_system_block_appears_before_symptoms() -> None:
    """The language/guidelines block must appear before the symptoms section."""
    pb = PromptBuilder()
    prompt = pb.build([], None, locale="fr-TG", region="TG")

    lang_pos = prompt.index("## Language and guidelines")
    symptoms_pos = prompt.index("## Symptoms")
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

    lang_pos = prompt.index("## Language and guidelines")
    profile_pos = prompt.index("## Patient profile")
    assert lang_pos < profile_pos, (
        "Language and guidelines block must precede the Patient profile section"
    )


def test_default_locale_is_fr_tg() -> None:
    """Default locale (no args) should produce French / CHU Lomé block."""
    pb = PromptBuilder()
    prompt = pb.build([], None)

    assert "- Respond in: French" in prompt
    assert "- Prioritise guidelines from: CHU Lomé (TG)" in prompt
    assert "- Region: (none)" in prompt
