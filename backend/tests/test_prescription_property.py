"""
Tests de propriété pour PrescriptionService et AlertService — Diagno-Pilot

**Validates: Requirements REQ-03, REQ-08, REQ-09**

Propriété 6 : Pour tout patient pédiatrique (non adulte) avec poids > 0,
la dose calculée est toujours ≤ dose adulte maximale
(is_capped_to_adult_dose = True si dépassement).

Propriété 7 : Toute prescription contenant un antibiotique figurant dans
les allergies connues du patient génère au minimum une alerte de niveau
`critical`.
"""
from __future__ import annotations

import asyncio

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.common import AgeGroup, AlertLevel
from backend.models.consultation import Prescription
from backend.models.patient import Comorbidities, PatientProfile
from backend.services.alert_service import AlertService
from backend.services.prescription_service import (
    ANTIBIOTIC_PROTOCOLS,
    PrescriptionService,
    _PAEDIATRIC_GROUPS,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Paediatric age groups only
paediatric_age_group_strategy = st.sampled_from(
    [AgeGroup.NEONATAL, AgeGroup.INFANT, AgeGroup.CHILD]
)

# Positive weight (0.5 kg – 100 kg covers neonates to large children)
positive_weight_strategy = st.floats(min_value=0.5, max_value=100.0, allow_nan=False, allow_infinity=False)

# Known antibiotic names from the protocol table
antibiotic_strategy = st.sampled_from(list(ANTIBIOTIC_PROTOCOLS.keys()))


def _make_paediatric_patient(age_group: AgeGroup, weight_kg: float) -> PatientProfile:
    return PatientProfile(
        full_name="Test Patient",
        weight_kg=weight_kg,
        age_group=age_group,
        allergies=[],
        comorbidities=Comorbidities(renal_failure=False, hepatic_failure=False),
        current_medications=[],
    )


# ---------------------------------------------------------------------------
# Property 6 : paediatric dose ≤ adult max dose
# ---------------------------------------------------------------------------

@given(
    antibiotic=antibiotic_strategy,
    age_group=paediatric_age_group_strategy,
    weight_kg=positive_weight_strategy,
)
@h_settings(max_examples=300)
def test_paediatric_dose_never_exceeds_adult_max(
    antibiotic: str,
    age_group: AgeGroup,
    weight_kg: float,
):
    """
    **Validates: Requirements REQ-03, REQ-08**

    For any paediatric patient (non-adult) with weight > 0, the calculated
    dose must always be ≤ the adult maximum dose, and is_capped_to_adult_dose
    must be True whenever the raw weight-based dose would exceed the adult max.
    """
    protocol = ANTIBIOTIC_PROTOCOLS[antibiotic]

    # Skip antibiotics contraindicated for this age group — they would raise
    # a ValueError in a real workflow (alert_service blocks them), but the
    # prescription_service itself still calculates the dose.
    # We test the dose property regardless of contraindication status.

    service = PrescriptionService()
    patient = _make_paediatric_patient(age_group, weight_kg)

    rx = asyncio.run(service.calculate_prescription(antibiotic=antibiotic, patient=patient))

    # The dose must never exceed the adult maximum
    assert rx.dose_mg <= protocol.adult_max_dose_mg, (
        f"dose_mg={rx.dose_mg} exceeds adult_max={protocol.adult_max_dose_mg} "
        f"for {antibiotic!r}, age_group={age_group.value}, weight={weight_kg}"
    )

    # is_capped_to_adult_dose must be True iff the raw dose would have exceeded the max
    raw_dose = protocol.paediatric_dose_per_kg * weight_kg
    expected_capped = raw_dose > protocol.adult_max_dose_mg

    assert rx.is_capped_to_adult_dose == expected_capped, (
        f"is_capped_to_adult_dose={rx.is_capped_to_adult_dose} but expected "
        f"{expected_capped} (raw_dose={raw_dose}, adult_max={protocol.adult_max_dose_mg})"
    )


# ---------------------------------------------------------------------------
# Property 7 : allergy → at least one critical alert
# ---------------------------------------------------------------------------

@given(antibiotic=antibiotic_strategy)
@h_settings(max_examples=200)
def test_allergy_always_generates_critical_alert(antibiotic: str):
    """
    **Validates: Requirements REQ-09**

    Any prescription containing an antibiotic that appears in the patient's
    known allergies must generate at least one alert of level CRITICAL.
    """
    # Build a patient whose allergy list contains the prescribed antibiotic
    patient = PatientProfile(
        full_name="Allergic Patient",
        weight_kg=70.0,
        age_group=AgeGroup.ADULT,
        allergies=[antibiotic],  # exact match
        comorbidities=Comorbidities(renal_failure=False, hepatic_failure=False),
        current_medications=[],
    )

    protocol = ANTIBIOTIC_PROTOCOLS[antibiotic]
    rx = Prescription(
        antibiotic=antibiotic,
        dose_mg=protocol.adult_max_dose_mg,
        frequency=protocol.frequency,
        duration_days=protocol.duration_days,
        route=protocol.route,
    )

    service = AlertService()
    alerts = asyncio.run(service.check_prescription(prescription=rx, patient=patient))

    critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]

    assert len(critical_alerts) >= 1, (
        f"Expected at least 1 CRITICAL alert for allergy to {antibiotic!r}, "
        f"got alerts: {alerts}"
    )


# ---------------------------------------------------------------------------
# Strategies for dose floor clamping tests
# ---------------------------------------------------------------------------

all_age_group_strategy = st.sampled_from(list(AgeGroup))

# Weight strategy that covers paediatric and adult ranges
weight_strategy = st.floats(min_value=0.5, max_value=120.0, allow_nan=False, allow_infinity=False)

# Custom floor percentage (1–100)
floor_pct_strategy = st.integers(min_value=1, max_value=100)


def _make_patient(
    age_group: AgeGroup,
    weight_kg: float,
    renal: bool,
    hepatic: bool,
) -> PatientProfile:
    return PatientProfile(
        full_name="Test Patient",
        weight_kg=weight_kg,
        age_group=age_group,
        allergies=[],
        comorbidities=Comorbidities(renal_failure=renal, hepatic_failure=hepatic),
        current_medications=[],
    )


# ---------------------------------------------------------------------------
# Property 11 : Prescription dose floor clamping
# ---------------------------------------------------------------------------

@given(
    antibiotic=antibiotic_strategy,
    age_group=all_age_group_strategy,
    weight_kg=weight_strategy,
)
@h_settings(max_examples=300)
def test_dose_floor_clamping_when_both_failures(
    antibiotic: str,
    age_group: AgeGroup,
    weight_kg: float,
):
    """
    **Property 11 — both failures present**
    **Validates: Requirements 17.1, 17.2, 17.4**

    When both renal and hepatic failure are present, the final dose must be
    at least pre_adjustment_dose × (min_dose_floor_pct / 100).
    """
    protocol = ANTIBIOTIC_PROTOCOLS[antibiotic]
    service = PrescriptionService()
    patient = _make_patient(age_group, weight_kg, renal=True, hepatic=True)

    rx = asyncio.run(service.calculate_prescription(antibiotic=antibiotic, patient=patient))

    # Compute expected pre-adjustment dose
    is_paediatric = age_group in _PAEDIATRIC_GROUPS
    if is_paediatric:
        raw_dose = protocol.paediatric_dose_per_kg * weight_kg
        pre_adj = min(raw_dose, protocol.adult_max_dose_mg)
    else:
        pre_adj = protocol.adult_max_dose_mg

    floor_pct = protocol.min_dose_floor_pct / 100.0
    min_dose = round(pre_adj * floor_pct, 2)

    assert rx.dose_mg >= min_dose - 0.01, (
        f"dose_mg={rx.dose_mg} below floor {min_dose} "
        f"(pre_adj={pre_adj}, floor_pct={protocol.min_dose_floor_pct}%) "
        f"for {antibiotic!r}, age_group={age_group.value}, weight={weight_kg}"
    )


@given(
    antibiotic=antibiotic_strategy,
    age_group=all_age_group_strategy,
    weight_kg=weight_strategy,
    renal_only=st.booleans(),
)
@h_settings(max_examples=300)
def test_no_clamping_when_single_failure(
    antibiotic: str,
    age_group: AgeGroup,
    weight_kg: float,
    renal_only: bool,
):
    """
    **Property 11 — single failure, no clamping**
    **Validates: Requirements 17.1, 17.4**

    When only one of renal or hepatic failure is present (not both),
    the dose equals the straightforward single-adjustment result with no
    floor clamping applied.
    """
    protocol = ANTIBIOTIC_PROTOCOLS[antibiotic]
    service = PrescriptionService()

    renal = renal_only
    hepatic = not renal_only
    patient = _make_patient(age_group, weight_kg, renal=renal, hepatic=hepatic)

    rx = asyncio.run(service.calculate_prescription(antibiotic=antibiotic, patient=patient))

    # Compute expected dose with single adjustment (no clamping)
    is_paediatric = age_group in _PAEDIATRIC_GROUPS
    if is_paediatric:
        raw_dose = protocol.paediatric_dose_per_kg * weight_kg
        pre_adj = min(raw_dose, protocol.adult_max_dose_mg)
    else:
        pre_adj = protocol.adult_max_dose_mg

    if renal:
        expected = pre_adj * protocol.renal_adjustment_factor
    else:
        expected = pre_adj * protocol.hepatic_adjustment_factor

    expected = max(expected, 0.0)

    assert abs(rx.dose_mg - round(expected, 2)) < 0.02, (
        f"dose_mg={rx.dose_mg} != expected {round(expected, 2)} "
        f"(single {'renal' if renal else 'hepatic'} adjustment) "
        f"for {antibiotic!r}, age_group={age_group.value}, weight={weight_kg}"
    )
