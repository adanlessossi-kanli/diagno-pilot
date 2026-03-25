"""
PrescriptionService — antibiotic prescription calculation (REQ-03, REQ-08, REQ-11).

Handles:
- Weight-based dose calculation (mg/kg) for paediatric age groups
- Capping to adult maximum dose (is_capped_to_adult_dose)
- Automatic adjustments for renal / hepatic failure
- Loading protocols from MongoDB with fallback to built-in dict (REQ 11.4, 11.5)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status

from backend.models.common import AgeGroup
from backend.models.consultation import Prescription
from backend.models.patient import PatientProfile

logger = logging.getLogger(__name__)


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


def _doc_to_protocol(doc: dict[str, Any]) -> AntibioticProtocol:
    """Convert a MongoDB document to an AntibioticProtocol dataclass."""
    contraindicated_raw = doc.get("contraindicated_age_groups", [])
    contraindicated = []
    for ag in contraindicated_raw:
        try:
            contraindicated.append(AgeGroup(ag))
        except ValueError:
            pass
    return AntibioticProtocol(
        name=doc["name"],
        paediatric_dose_per_kg=float(doc["paediatric_dose_per_kg"]),
        adult_max_dose_mg=float(doc["adult_max_dose_mg"]),
        frequency=doc["frequency"],
        duration_days=int(doc["duration_days"]),
        route=doc["route"],
        renal_adjustment_factor=float(doc.get("renal_adjustment_factor", 1.0)),
        hepatic_adjustment_factor=float(doc.get("hepatic_adjustment_factor", 1.0)),
        contraindicated_age_groups=contraindicated,
        alternative=doc.get("alternative"),
    )


class PrescriptionService:
    """Calculates antibiotic prescriptions adapted to the patient profile.

    Protocols are loaded from MongoDB at startup (REQ 11.4) with fallback to
    the built-in ANTIBIOTIC_PROTOCOLS dict if the collection is empty (REQ 11.5).
    """

    def __init__(self) -> None:
        # In-memory cache: name → AntibioticProtocol (populated from DB or fallback)
        self._protocols_cache: dict[str, AntibioticProtocol] = {}

    async def load_protocols_from_db(self) -> None:
        """Load antibiotic protocols from MongoDB into the in-memory cache.

        Falls back to the built-in ANTIBIOTIC_PROTOCOLS dict if the collection
        is empty (REQ 11.5).
        """
        from backend.core.database import db

        try:
            database = db.get_db()
            cursor = database["antibiotic_protocols"].find({})
            docs = await cursor.to_list(length=None)
        except Exception:
            logger.warning(
                "Failed to load protocols from MongoDB; using built-in fallback",
                exc_info=True,
            )
            docs = []

        if docs:
            self._protocols_cache = {doc["name"]: _doc_to_protocol(doc) for doc in docs}
            logger.info(
                "PrescriptionService: loaded %d protocols from MongoDB",
                len(self._protocols_cache),
            )
        else:
            self._protocols_cache = dict(ANTIBIOTIC_PROTOCOLS)
            logger.warning(
                "PrescriptionService: antibiotic_protocols collection is empty; "
                "using built-in fallback (%d protocols)",
                len(self._protocols_cache),
            )

    async def reload_protocols(self) -> None:
        """Refresh the in-memory cache from MongoDB.

        Called after each PUT/POST admin operation (REQ 11.4).
        """
        await self.load_protocols_from_db()

    def _get_protocol(self, key: str) -> AntibioticProtocol:
        """Look up a protocol: DB cache first, then built-in dict.

        Raises HTTPException 422 with 'unknown_antibiotic' if not found (REQ 11.5).
        """
        # DB cache (populated at startup or after reload)
        protocol = self._protocols_cache.get(key)
        if protocol is not None:
            return protocol
        # Fallback to built-in dict (in case cache was never loaded)
        protocol = ANTIBIOTIC_PROTOCOLS.get(key)
        if protocol is not None:
            return protocol
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unknown_antibiotic",
        )

    def calculate_prescription(
        self,
        antibiotic: str,
        patient: PatientProfile,
    ) -> Prescription:
        """Return a Prescription adapted to the patient's weight, age group,
        and comorbidities.

        Args:
            antibiotic: Antibiotic name (case-insensitive key).
            patient: Patient profile with weight, age group, and comorbidities.

        Returns:
            A Prescription with dose_mg, dose_per_kg (if paediatric),
            is_capped_to_adult_dose, frequency, duration_days, and route.

        Raises:
            HTTPException 422: If the antibiotic is unknown (REQ 11.5).
            ValueError: If weight is required but missing.
        """
        key = antibiotic.lower()
        protocol = self._get_protocol(key)

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
