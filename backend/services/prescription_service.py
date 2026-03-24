"""
PrescriptionService — antibiotic prescription calculation (REQ-03, REQ-08).

Handles:
- Weight-based dose calculation (mg/kg) for paediatric age groups
- Capping to adult maximum dose (is_capped_to_adult_dose)
- Automatic adjustments for renal / hepatic failure
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.models.common import AgeGroup
from backend.models.consultation import Prescription
from backend.models.patient import PatientProfile


@dataclass
class AntibioticProtocol:
    """Dosing protocol for a single antibiotic."""
    name: str
    # Paediatric dose in mg/kg/day
    paediatric_dose_per_kg: float
    # Adult maximum daily dose in mg
    adult_max_dose_mg: float
    # Default frequency string
    frequency: str
    # Default duration in days
    duration_days: int
    # Default route
    route: str
    # Dose reduction factor for renal failure (0–1)
    renal_adjustment_factor: float = 1.0
    # Dose reduction factor for hepatic failure (0–1)
    hepatic_adjustment_factor: float = 1.0
    # Age groups where this antibiotic is contraindicated
    contraindicated_age_groups: list[AgeGroup] = field(default_factory=list)
    # Suggested alternative when contraindicated
    alternative: str | None = None


# ---------------------------------------------------------------------------
# Built-in antibiotic protocols (representative subset for REQ-03 / REQ-08)
# ---------------------------------------------------------------------------

ANTIBIOTIC_PROTOCOLS: dict[str, AntibioticProtocol] = {
    "amoxicillin": AntibioticProtocol(
        name="amoxicillin",
        paediatric_dose_per_kg=50.0,
        adult_max_dose_mg=3000.0,
        frequency="3x/day",
        duration_days=7,
        route="oral",
        renal_adjustment_factor=0.5,
    ),
    "amoxicillin-clavulanate": AntibioticProtocol(
        name="amoxicillin-clavulanate",
        paediatric_dose_per_kg=45.0,
        adult_max_dose_mg=2625.0,
        frequency="3x/day",
        duration_days=7,
        route="oral",
        renal_adjustment_factor=0.5,
    ),
    "ceftriaxone": AntibioticProtocol(
        name="ceftriaxone",
        paediatric_dose_per_kg=50.0,
        adult_max_dose_mg=2000.0,
        frequency="1x/day",
        duration_days=7,
        route="IV",
        renal_adjustment_factor=0.75,
    ),
    "ciprofloxacin": AntibioticProtocol(
        name="ciprofloxacin",
        paediatric_dose_per_kg=20.0,
        adult_max_dose_mg=1500.0,
        frequency="2x/day",
        duration_days=7,
        route="oral",
        renal_adjustment_factor=0.5,
        contraindicated_age_groups=[AgeGroup.NEONATAL, AgeGroup.INFANT, AgeGroup.CHILD],
        alternative="ceftriaxone",
    ),
    "metronidazole": AntibioticProtocol(
        name="metronidazole",
        paediatric_dose_per_kg=30.0,
        adult_max_dose_mg=2000.0,
        frequency="3x/day",
        duration_days=7,
        route="oral",
        hepatic_adjustment_factor=0.5,
    ),
    "azithromycin": AntibioticProtocol(
        name="azithromycin",
        paediatric_dose_per_kg=10.0,
        adult_max_dose_mg=500.0,
        frequency="1x/day",
        duration_days=5,
        route="oral",
        hepatic_adjustment_factor=0.75,
    ),
    "doxycycline": AntibioticProtocol(
        name="doxycycline",
        paediatric_dose_per_kg=4.0,
        adult_max_dose_mg=200.0,
        frequency="2x/day",
        duration_days=7,
        route="oral",
        contraindicated_age_groups=[AgeGroup.NEONATAL, AgeGroup.INFANT, AgeGroup.CHILD],
        alternative="azithromycin",
    ),
    "cotrimoxazole": AntibioticProtocol(
        name="cotrimoxazole",
        paediatric_dose_per_kg=48.0,
        adult_max_dose_mg=1920.0,
        frequency="2x/day",
        duration_days=5,
        route="oral",
        renal_adjustment_factor=0.5,
    ),
    "gentamicin": AntibioticProtocol(
        name="gentamicin",
        paediatric_dose_per_kg=5.0,
        adult_max_dose_mg=240.0,
        frequency="1x/day",
        duration_days=7,
        route="IV",
        renal_adjustment_factor=0.25,
    ),
    "penicillin-v": AntibioticProtocol(
        name="penicillin-v",
        paediatric_dose_per_kg=50.0,
        adult_max_dose_mg=2000.0,
        frequency="4x/day",
        duration_days=10,
        route="oral",
        renal_adjustment_factor=0.5,
    ),
}

# Paediatric age groups (non-adult)
_PAEDIATRIC_GROUPS = {AgeGroup.NEONATAL, AgeGroup.INFANT, AgeGroup.CHILD}


class PrescriptionService:
    """Calculates antibiotic prescriptions adapted to the patient profile."""

    def calculate_prescription(
        self,
        antibiotic: str,
        patient: PatientProfile,
    ) -> Prescription:
        """Return a Prescription adapted to the patient's weight, age group,
        and comorbidities.

        Args:
            antibiotic: Antibiotic name (case-insensitive key in ANTIBIOTIC_PROTOCOLS).
            patient: Patient profile with weight, age group, and comorbidities.

        Returns:
            A Prescription with dose_mg, dose_per_kg (if paediatric),
            is_capped_to_adult_dose, frequency, duration_days, and route.

        Raises:
            ValueError: If the antibiotic is unknown or weight is required but missing.
        """
        key = antibiotic.lower()
        protocol = ANTIBIOTIC_PROTOCOLS.get(key)
        if protocol is None:
            # Unknown antibiotic — use a generic adult dose of 0 as placeholder
            # so callers can still handle the response; raise for strict usage.
            raise ValueError(f"Unknown antibiotic: {antibiotic!r}")

        age_group = patient.age_group
        is_paediatric = age_group in _PAEDIATRIC_GROUPS

        is_capped = False
        dose_per_kg: float | None = None

        if is_paediatric:
            weight = patient.weight_kg
            if weight is None or weight <= 0:
                raise ValueError(
                    "weight_kg must be a positive number for paediatric dose calculation"
                )
            raw_dose = protocol.paediatric_dose_per_kg * weight
            dose_per_kg = protocol.paediatric_dose_per_kg

            if raw_dose > protocol.adult_max_dose_mg:
                dose_mg = protocol.adult_max_dose_mg
                is_capped = True
            else:
                dose_mg = raw_dose
        else:
            # Adult: use adult max dose directly
            dose_mg = protocol.adult_max_dose_mg

        # Apply renal adjustment
        renal_failure = (
            patient.comorbidities.renal_failure
            if patient.comorbidities
            else False
        )
        hepatic_failure = (
            patient.comorbidities.hepatic_failure
            if patient.comorbidities
            else False
        )

        if renal_failure:
            dose_mg *= protocol.renal_adjustment_factor
        if hepatic_failure:
            dose_mg *= protocol.hepatic_adjustment_factor

        # Ensure dose is positive after adjustments
        dose_mg = max(dose_mg, 0.0)

        return Prescription(
            antibiotic=protocol.name,
            dose_mg=round(dose_mg, 2),
            dose_per_kg=dose_per_kg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
            is_capped_to_adult_dose=is_capped,
        )


# Module-level singleton
prescription_service = PrescriptionService()
