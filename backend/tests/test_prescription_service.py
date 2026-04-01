"""
Tests unitaires pour PrescriptionService et AlertService — Diagno-Pilot

Couvre : calcul de dose pédiatrique, plafonnement, ajustements rénaux/hépatiques,
         alertes d'allergie, interactions, contre-indications par âge.

Requirements: REQ-03, REQ-08, REQ-09
"""
from __future__ import annotations

import asyncio

import pytest

from backend.models.common import AgeGroup, AlertLevel
from backend.models.consultation import Prescription
from backend.models.patient import Comorbidities, PatientProfile
from backend.services.alert_service import AlertService
from backend.services.prescription_service import (
    ANTIBIOTIC_PROTOCOLS,
    AntibioticProtocol,
    PrescriptionService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patient(
    age_group: AgeGroup = AgeGroup.ADULT,
    weight_kg: float | None = 70.0,
    allergies: list[str] | None = None,
    renal_failure: bool = False,
    hepatic_failure: bool = False,
    current_medications: list[str] | None = None,
) -> PatientProfile:
    return PatientProfile(
        full_name="Test Patient",
        weight_kg=weight_kg,
        age_group=age_group,
        allergies=allergies or [],
        comorbidities=Comorbidities(
            renal_failure=renal_failure,
            hepatic_failure=hepatic_failure,
        ),
        current_medications=current_medications or [],
    )


# ---------------------------------------------------------------------------
# PrescriptionService — dose calculation
# ---------------------------------------------------------------------------

class TestPrescriptionServiceDoseCalculation:

    def test_adult_dose_equals_adult_max(self):
        """Adult patient receives the adult maximum dose."""
        svc = PrescriptionService()
        rx = asyncio.run(svc.calculate_prescription("amoxicillin", _patient(AgeGroup.ADULT, 70.0)))
        assert rx.dose_mg == ANTIBIOTIC_PROTOCOLS["amoxicillin"].adult_max_dose_mg
        assert rx.is_capped_to_adult_dose is False
        assert rx.dose_per_kg is None

    def test_paediatric_dose_calculated_from_weight(self):
        """Child patient: dose = dose_per_kg × weight."""
        svc = PrescriptionService()
        # 10 kg child: 50 mg/kg × 10 = 500 mg < 3000 mg adult max
        rx = asyncio.run(svc.calculate_prescription("amoxicillin", _patient(AgeGroup.CHILD, 10.0)))
        assert rx.dose_mg == pytest.approx(500.0)
        assert rx.dose_per_kg == 50.0
        assert rx.is_capped_to_adult_dose is False

    def test_paediatric_dose_capped_to_adult_max(self):
        """Heavy child: dose is capped to adult max and flag is set."""
        svc = PrescriptionService()
        # 80 kg child: 50 × 80 = 4000 mg > 3000 mg → capped
        rx = asyncio.run(svc.calculate_prescription("amoxicillin", _patient(AgeGroup.CHILD, 80.0)))
        assert rx.dose_mg == ANTIBIOTIC_PROTOCOLS["amoxicillin"].adult_max_dose_mg
        assert rx.is_capped_to_adult_dose is True

    def test_neonatal_dose_calculated(self):
        """Neonatal patient (3 kg): dose = dose_per_kg × weight."""
        svc = PrescriptionService()
        rx = asyncio.run(svc.calculate_prescription("amoxicillin", _patient(AgeGroup.NEONATAL, 3.0)))
        assert rx.dose_mg == pytest.approx(150.0)
        assert rx.is_capped_to_adult_dose is False

    def test_infant_dose_calculated(self):
        """Infant patient (7 kg): dose = dose_per_kg × weight."""
        svc = PrescriptionService()
        rx = asyncio.run(svc.calculate_prescription("amoxicillin", _patient(AgeGroup.INFANT, 7.0)))
        assert rx.dose_mg == pytest.approx(350.0)
        assert rx.is_capped_to_adult_dose is False

    def test_renal_failure_reduces_dose(self):
        """Renal failure applies the renal adjustment factor."""
        svc = PrescriptionService()
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
        rx = asyncio.run(svc.calculate_prescription(
            "amoxicillin", _patient(AgeGroup.ADULT, 70.0, renal_failure=True)
        ))
        expected = protocol.adult_max_dose_mg * protocol.renal_adjustment_factor
        assert rx.dose_mg == pytest.approx(expected)

    def test_hepatic_failure_reduces_dose(self):
        """Hepatic failure applies the hepatic adjustment factor."""
        svc = PrescriptionService()
        protocol = ANTIBIOTIC_PROTOCOLS["metronidazole"]
        rx = asyncio.run(svc.calculate_prescription(
            "metronidazole", _patient(AgeGroup.ADULT, 70.0, hepatic_failure=True)
        ))
        expected = protocol.adult_max_dose_mg * protocol.hepatic_adjustment_factor
        assert rx.dose_mg == pytest.approx(expected)

    def test_both_failures_stack(self):
        """Both renal and hepatic failure factors are applied multiplicatively."""
        svc = PrescriptionService()
        # Use an antibiotic with both adjustments < 1 — create a custom scenario
        # amoxicillin has renal_adjustment_factor=0.5, hepatic=1.0
        # metronidazole has hepatic=0.5, renal=1.0
        # For stacking, use amoxicillin with both flags (hepatic factor is 1.0 so no change)
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
        rx = asyncio.run(svc.calculate_prescription(
            "amoxicillin",
            _patient(AgeGroup.ADULT, 70.0, renal_failure=True, hepatic_failure=True),
        ))
        expected = (
            protocol.adult_max_dose_mg
            * protocol.renal_adjustment_factor
            * protocol.hepatic_adjustment_factor
        )
        assert rx.dose_mg == pytest.approx(expected)

    def test_unknown_antibiotic_raises_value_error(self):
        """Unknown antibiotic raises HTTPException 422 with 'unknown_antibiotic'."""
        from fastapi import HTTPException
        svc = PrescriptionService()
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(svc.calculate_prescription("unknown_drug_xyz", _patient()))
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "unknown_antibiotic"

    def test_paediatric_without_weight_raises_value_error(self):
        """Paediatric patient without weight raises ValueError."""
        svc = PrescriptionService()
        with pytest.raises(ValueError, match="weight_kg"):
            asyncio.run(svc.calculate_prescription(
                "amoxicillin", _patient(AgeGroup.CHILD, weight_kg=None)
            ))

    def test_prescription_fields_populated(self):
        """Prescription contains all required fields."""
        svc = PrescriptionService()
        rx = asyncio.run(svc.calculate_prescription("ceftriaxone", _patient(AgeGroup.ADULT)))
        assert rx.antibiotic == "ceftriaxone"
        assert rx.frequency
        assert rx.duration_days > 0
        assert rx.route in ("oral", "IV", "IM")


# ---------------------------------------------------------------------------
# AlertService — allergy checks
# ---------------------------------------------------------------------------

class TestAlertServiceAllergies:

    def test_allergy_match_generates_critical_alert(self):
        """Exact allergy match → CRITICAL alert."""
        svc = AlertService()
        patient = _patient(allergies=["amoxicillin"])
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
        rx = Prescription(
            antibiotic="amoxicillin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )
        alerts = asyncio.run(svc.check_prescription(rx, patient))
        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL and a.type == "allergy"]
        assert len(critical) >= 1

    def test_no_allergy_no_critical_alert(self):
        """No allergy → no allergy-type critical alert."""
        svc = AlertService()
        patient = _patient(allergies=[])
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
        rx = Prescription(
            antibiotic="amoxicillin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )
        alerts = asyncio.run(svc.check_prescription(rx, patient))
        allergy_alerts = [a for a in alerts if a.type == "allergy"]
        assert len(allergy_alerts) == 0

    def test_allergy_alert_contains_alternative(self):
        """Allergy alert for ciprofloxacin includes an alternative."""
        svc = AlertService()
        patient = _patient(allergies=["ciprofloxacin"])
        protocol = ANTIBIOTIC_PROTOCOLS["ciprofloxacin"]
        rx = Prescription(
            antibiotic="ciprofloxacin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )
        alerts = asyncio.run(svc.check_prescription(rx, patient))
        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL and a.type == "allergy"]
        assert len(critical) >= 1
        assert critical[0].alternative is not None


# ---------------------------------------------------------------------------
# AlertService — age contraindications
# ---------------------------------------------------------------------------

class TestAlertServiceAgeContraindications:

    def test_fluoroquinolone_contraindicated_in_child(self):
        """Ciprofloxacin is contraindicated for children → CRITICAL alert."""
        svc = AlertService()
        patient = _patient(AgeGroup.CHILD, 20.0)
        protocol = ANTIBIOTIC_PROTOCOLS["ciprofloxacin"]
        rx = Prescription(
            antibiotic="ciprofloxacin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )
        alerts = asyncio.run(svc.check_prescription(rx, patient))
        critical = [
            a for a in alerts
            if a.level == AlertLevel.CRITICAL and a.type == "contraindication"
        ]
        assert len(critical) >= 1
        assert critical[0].alternative is not None

    def test_no_contraindication_for_adult(self):
        """Ciprofloxacin is not contraindicated for adults → no contraindication alert."""
        svc = AlertService()
        patient = _patient(AgeGroup.ADULT, 70.0)
        protocol = ANTIBIOTIC_PROTOCOLS["ciprofloxacin"]
        rx = Prescription(
            antibiotic="ciprofloxacin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )
        alerts = asyncio.run(svc.check_prescription(rx, patient))
        contraindication_alerts = [a for a in alerts if a.type == "contraindication"]
        assert len(contraindication_alerts) == 0


# ---------------------------------------------------------------------------
# AlertService — organ failure warnings
# ---------------------------------------------------------------------------

class TestAlertServiceOrganFailure:

    def test_renal_failure_generates_warning(self):
        """Renal failure with dose-adjusted antibiotic → WARNING alert."""
        svc = AlertService()
        patient = _patient(AgeGroup.ADULT, 70.0, renal_failure=True)
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
        rx = Prescription(
            antibiotic="amoxicillin",
            dose_mg=protocol.adult_max_dose_mg * protocol.renal_adjustment_factor,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )
        alerts = asyncio.run(svc.check_prescription(rx, patient))
        warnings = [a for a in alerts if a.level == AlertLevel.WARNING]
        assert len(warnings) >= 1

    def test_hepatic_failure_generates_warning(self):
        """Hepatic failure with dose-adjusted antibiotic → WARNING alert."""
        svc = AlertService()
        patient = _patient(AgeGroup.ADULT, 70.0, hepatic_failure=True)
        protocol = ANTIBIOTIC_PROTOCOLS["metronidazole"]
        rx = Prescription(
            antibiotic="metronidazole",
            dose_mg=protocol.adult_max_dose_mg * protocol.hepatic_adjustment_factor,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )
        alerts = asyncio.run(svc.check_prescription(rx, patient))
        warnings = [a for a in alerts if a.level == AlertLevel.WARNING]
        assert len(warnings) >= 1

    def test_no_organ_failure_no_organ_warning(self):
        """No organ failure → no organ-failure warning."""
        svc = AlertService()
        patient = _patient(AgeGroup.ADULT, 70.0)
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
        rx = Prescription(
            antibiotic="amoxicillin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )
        alerts = asyncio.run(svc.check_prescription(rx, patient))
        # No organ-failure warnings expected (no allergies, no interactions, no contraindications)
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# AlertService — drug interactions
# ---------------------------------------------------------------------------

class TestAlertServiceInteractions:

    def test_known_interaction_generates_warning(self):
        """Ciprofloxacin + warfarin → WARNING interaction alert."""
        svc = AlertService()
        patient = _patient(
            AgeGroup.ADULT, 70.0, current_medications=["warfarin"]
        )
        protocol = ANTIBIOTIC_PROTOCOLS["ciprofloxacin"]
        rx = Prescription(
            antibiotic="ciprofloxacin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )
        alerts = asyncio.run(svc.check_prescription(rx, patient))
        interaction_alerts = [
            a for a in alerts if a.type == "interaction" and a.level == AlertLevel.WARNING
        ]
        assert len(interaction_alerts) >= 1

    def test_no_interaction_no_warning(self):
        """No current medications → no interaction warning."""
        svc = AlertService()
        patient = _patient(AgeGroup.ADULT, 70.0, current_medications=[])
        protocol = ANTIBIOTIC_PROTOCOLS["ciprofloxacin"]
        rx = Prescription(
            antibiotic="ciprofloxacin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )
        alerts = asyncio.run(svc.check_prescription(rx, patient))
        interaction_alerts = [a for a in alerts if a.type == "interaction"]
        assert len(interaction_alerts) == 0


# ---------------------------------------------------------------------------
# Property-based test — P14: PrescriptionService priorité DB sur dict codé en dur
# ---------------------------------------------------------------------------

from hypothesis import given, settings, HealthCheck  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

settings.register_profile("ci", max_examples=100, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("ci")


class TestPrescriptionServiceDBPriority:
    """
    # Feature: diagno-pilot-improvements, Property 14: PrescriptionService utilise la version DB en priorité sur le dict codé en dur
    """

    @given(
        protocol_name=st.sampled_from(sorted(ANTIBIOTIC_PROTOCOLS.keys())),
        db_adult_max_dose=st.floats(min_value=100.0, max_value=9999.0, allow_nan=False, allow_infinity=False),
    )
    def test_db_protocol_takes_priority_over_hardcoded(
        self,
        protocol_name: str,
        db_adult_max_dose: float,
    ):
        """
        **Validates: Requirements 11.4**

        For any antibiotic protocol present in ANTIBIOTIC_PROTOCOLS, if the
        _protocols_cache is populated with a modified version (different
        adult_max_dose_mg), calculate_prescription() must use the DB (cache)
        values rather than the hardcoded dict values.
        """
        hardcoded_dose = ANTIBIOTIC_PROTOCOLS[protocol_name].adult_max_dose_mg

        # Ensure the DB dose is meaningfully different from the hardcoded dose
        # to make the assertion meaningful
        if abs(db_adult_max_dose - hardcoded_dose) < 1.0:
            db_adult_max_dose = hardcoded_dose + 500.0

        # Build a modified protocol with the DB dose
        hardcoded_protocol = ANTIBIOTIC_PROTOCOLS[protocol_name]
        db_protocol = AntibioticProtocol(
            name=hardcoded_protocol.name,
            paediatric_dose_per_kg=hardcoded_protocol.paediatric_dose_per_kg,
            adult_max_dose_mg=db_adult_max_dose,
            frequency=hardcoded_protocol.frequency,
            duration_days=hardcoded_protocol.duration_days,
            route=hardcoded_protocol.route,
            renal_adjustment_factor=hardcoded_protocol.renal_adjustment_factor,
            hepatic_adjustment_factor=hardcoded_protocol.hepatic_adjustment_factor,
            contraindicated_age_groups=list(hardcoded_protocol.contraindicated_age_groups),
            alternative=hardcoded_protocol.alternative,
        )

        # Create a fresh service and populate the cache with the DB version
        svc = PrescriptionService()
        svc._protocols_cache = {protocol_name: db_protocol}

        # Use an adult patient (no weight-based calculation, uses adult_max_dose_mg directly)
        patient = _patient(AgeGroup.ADULT, weight_kg=70.0)

        rx = asyncio.run(svc.calculate_prescription(protocol_name, patient))

        # The prescription must use the DB dose, not the hardcoded one
        assert rx.dose_mg == pytest.approx(round(db_adult_max_dose, 2)), (
            f"Expected DB dose {db_adult_max_dose} but got {rx.dose_mg} "
            f"(hardcoded was {hardcoded_dose})"
        )
        assert rx.dose_mg != pytest.approx(hardcoded_dose) or abs(db_adult_max_dose - hardcoded_dose) < 0.01
