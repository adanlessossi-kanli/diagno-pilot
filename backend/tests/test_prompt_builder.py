"""Tests for PromptBuilder — code-quality spec, Task 1.

Covers:
- 1.1  Property 1: PromptBuilder is a pure function (Hypothesis)
- 1.2  Property 2: PromptBuilder includes patient profile fields (Hypothesis)
- 1.3  Unit tests for PromptBuilder
"""
from __future__ import annotations

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.common import AgeGroup
from backend.models.consultation import Symptom
from backend.models.patient import Comorbidities, PatientProfile
from backend.services.prompt_builder import PromptBuilder

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

severity_st = st.sampled_from(["mild", "moderate", "severe"])

symptom_st = st.builds(
    Symptom,
    name=st.text(min_size=1, max_size=50).filter(str.strip),
    severity=st.one_of(st.none(), severity_st),
    duration_days=st.one_of(st.none(), st.integers(min_value=0, max_value=365)),
)

symptoms_st = st.lists(symptom_st, min_size=0, max_size=10)

age_group_st = st.one_of(st.none(), st.sampled_from(list(AgeGroup)))

comorbidities_st = st.builds(
    Comorbidities,
    renal_failure=st.booleans(),
    hepatic_failure=st.booleans(),
)

patient_profile_st = st.builds(
    PatientProfile,
    full_name=st.one_of(st.none(), st.text(min_size=1, max_size=50).filter(str.strip)),
    date_of_birth=st.none(),  # avoid triggering age_group auto-compute
    weight_kg=st.one_of(st.none(), st.floats(min_value=0.1, max_value=300.0, allow_nan=False)),
    age_group=age_group_st,
    allergies=st.lists(st.text(min_size=1, max_size=30).filter(str.strip), max_size=5),
    comorbidities=comorbidities_st,
    current_medications=st.lists(st.text(min_size=1, max_size=30), max_size=3),
)

profile_or_none_st = st.one_of(st.none(), patient_profile_st)


# ---------------------------------------------------------------------------
# 1.1  Property 1: PromptBuilder is a pure function
# **Validates: Requirements 1.1, 1.5**
# ---------------------------------------------------------------------------

@given(symptoms=symptoms_st, profile=profile_or_none_st)
@h_settings(max_examples=100)
def test_prompt_builder_pure(symptoms: list[Symptom], profile: PatientProfile | None) -> None:
    """Feature: code-quality, Property 1: PromptBuilder is a pure function.

    Calling build() twice with identical arguments must return identical strings.

    **Validates: Requirements 1.1, 1.5**
    """
    pb = PromptBuilder()
    result1 = pb.build(symptoms, profile)
    result2 = pb.build(symptoms, profile)
    assert result1 == result2, (
        "PromptBuilder.build() returned different strings for the same inputs — "
        "it must be a pure, side-effect-free function."
    )


# ---------------------------------------------------------------------------
# 1.2  Property 2: PromptBuilder includes patient profile fields
# **Validates: Requirements 1.2, 1.4**
# ---------------------------------------------------------------------------

@given(profile=patient_profile_st)
@h_settings(max_examples=100)
def test_prompt_includes_profile_fields(profile: PatientProfile) -> None:
    """Feature: code-quality, Property 2: PromptBuilder includes patient profile fields.

    For any patient profile with non-None age group, weight, comorbidities, or
    allergies, the returned prompt must contain each of those field values as a
    substring.

    **Validates: Requirements 1.2, 1.4**
    """
    pb = PromptBuilder()
    prompt = pb.build([], profile)

    if profile.age_group is not None:
        assert profile.age_group.value in prompt, (
            f"age_group value {profile.age_group.value!r} not found in prompt"
        )

    if profile.weight_kg is not None:
        assert str(profile.weight_kg) in prompt, (
            f"weight_kg value {profile.weight_kg!r} not found in prompt"
        )

    for allergy in profile.allergies:
        assert allergy in prompt, (
            f"allergy {allergy!r} not found in prompt"
        )

    if profile.comorbidities.renal_failure:
        assert "renal failure" in prompt, "renal failure not found in prompt"

    if profile.comorbidities.hepatic_failure:
        assert "hepatic failure" in prompt, "hepatic failure not found in prompt"


# ---------------------------------------------------------------------------
# 1.3  Unit tests for PromptBuilder
# Requirements: 1.1, 1.2, 1.3
# ---------------------------------------------------------------------------

def _make_full_profile() -> PatientProfile:
    return PatientProfile(
        full_name="Jane Doe",
        date_of_birth=None,
        weight_kg=65.0,
        age_group=AgeGroup.ADULT,
        allergies=["penicillin", "sulfonamides"],
        comorbidities=Comorbidities(renal_failure=True, hepatic_failure=False),
        current_medications=["metformin"],
    )


def _make_symptoms() -> list[Symptom]:
    return [
        Symptom(name="fever", severity="moderate", duration_days=3),
        Symptom(name="cough", severity="mild", duration_days=7),
    ]


def test_build_with_full_profile_contains_all_fields() -> None:
    """build() with a full patient profile must include all profile fields."""
    pb = PromptBuilder()
    profile = _make_full_profile()
    symptoms = _make_symptoms()

    prompt = pb.build(symptoms, profile)

    # Patient profile section header
    assert "## Patient profile" in prompt

    # Age group
    assert AgeGroup.ADULT.value in prompt  # "adult"

    # Weight
    assert "65.0" in prompt

    # Comorbidities
    assert "renal failure" in prompt

    # Allergies
    assert "penicillin" in prompt
    assert "sulfonamides" in prompt

    # Symptoms section
    assert "## Symptoms" in prompt
    assert "fever" in prompt
    assert "cough" in prompt

    # JSON instruction
    assert "JSON array" in prompt
    assert "AT LEAST 3" in prompt


def test_build_without_profile_has_no_patient_section() -> None:
    """build() with patient_profile=None must omit the patient section."""
    pb = PromptBuilder()
    symptoms = _make_symptoms()

    prompt = pb.build(symptoms, None)

    # No patient profile section
    assert "## Patient profile" not in prompt

    # Symptoms section must still be present
    assert "## Symptoms" in prompt
    assert "fever" in prompt
    assert "cough" in prompt

    # JSON instruction must still be present
    assert "JSON array" in prompt


def test_build_symptoms_section_includes_severity_and_duration() -> None:
    """Symptom entries must include severity and duration when present."""
    pb = PromptBuilder()
    symptoms = [Symptom(name="headache", severity="severe", duration_days=2)]

    prompt = pb.build(symptoms, None)

    assert "headache" in prompt
    assert "severity=severe" in prompt
    assert "duration=2d" in prompt


def test_build_symptom_without_optional_fields() -> None:
    """Symptom with no severity/duration must still appear in the prompt."""
    pb = PromptBuilder()
    symptoms = [Symptom(name="fatigue")]

    prompt = pb.build(symptoms, None)

    assert "fatigue" in prompt
    # No severity= or duration= fragments
    assert "severity=" not in prompt
    assert "duration=" not in prompt


def test_build_json_instruction_present() -> None:
    """The JSON-array instruction paragraph must always be present."""
    pb = PromptBuilder()
    prompt = pb.build([], None)

    assert "JSON array" in prompt
    assert "AT LEAST 3" in prompt
    assert "descending probability" in prompt
