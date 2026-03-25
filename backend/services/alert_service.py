"""
AlertService — safety alert checking for antibiotic prescriptions (REQ-09).

Checks:
- Known patient allergies (critical)
- Drug interactions with current medications (warning)
- Age-based contraindications (critical)
- Organ failure contraindications (warning)

REQ 12: Drug interactions loaded from MongoDB `drug_interactions` collection at startup.
"""
from __future__ import annotations

import logging

from backend.models.alert import SafetyAlert
from backend.models.common import AgeGroup, AlertLevel
from backend.models.consultation import Prescription
from backend.models.patient import PatientProfile
from backend.services.prescription_service import ANTIBIOTIC_PROTOCOLS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known drug interaction pairs (symmetric) — hardcoded fallback (REQ 12.5)
# Each entry: (drug_a_lower, drug_b_lower, message)
# ---------------------------------------------------------------------------

_DRUG_INTERACTIONS: list[tuple[str, str, str]] = [
    (
        "ciprofloxacin",
        "metronidazole",
        "Risque accru de prolongation QT avec ciprofloxacine + métronidazole.",
    ),
    (
        "doxycycline",
        "antacids",
        "Les antiacides réduisent l'absorption de la doxycycline.",
    ),
    (
        "metronidazole",
        "warfarin",
        "Le métronidazole potentialise l'effet anticoagulant de la warfarine.",
    ),
    (
        "ciprofloxacin",
        "warfarin",
        "La ciprofloxacine potentialise l'effet anticoagulant de la warfarine.",
    ),
    (
        "azithromycin",
        "warfarin",
        "L'azithromycine peut potentialiser l'effet anticoagulant de la warfarine.",
    ),
    (
        "gentamicin",
        "furosemide",
        "Association néphrotoxique et ototoxique : gentamicine + furosémide.",
    ),
    (
        "gentamicin",
        "vancomycin",
        "Association néphrotoxique : gentamicine + vancomycine.",
    ),
    (
        "cotrimoxazole",
        "warfarin",
        "Le cotrimoxazole potentialise l'effet anticoagulant de la warfarine.",
    ),
]

# Paediatric age groups
_PAEDIATRIC_GROUPS = {AgeGroup.NEONATAL, AgeGroup.INFANT, AgeGroup.CHILD}


class AlertService:
    """Checks a prescription against a patient profile and returns safety alerts."""

    def __init__(self) -> None:
        # In-memory cache of interactions: list of (drug_a, drug_b, message)
        self._interactions_cache: list[tuple[str, str, str]] = list(_DRUG_INTERACTIONS)

    async def load_interactions_from_db(self) -> None:
        """Load drug interactions from MongoDB `drug_interactions` collection.

        Falls back to the built-in _DRUG_INTERACTIONS list if the collection
        is empty (REQ 12.5).
        """
        from backend.core.database import db

        try:
            database = db.get_db()
            cursor = database["drug_interactions"].find({})
            docs = await cursor.to_list(length=None)
        except Exception:
            logger.warning(
                "Failed to load drug interactions from MongoDB; using built-in fallback",
                exc_info=True,
            )
            docs = []

        if docs:
            self._interactions_cache = [
                (doc["drug_a"].lower(), doc["drug_b"].lower(), doc["message"])
                for doc in docs
            ]
            logger.info(
                "AlertService: loaded %d drug interactions from MongoDB",
                len(self._interactions_cache),
            )
        else:
            self._interactions_cache = list(_DRUG_INTERACTIONS)
            logger.warning(
                "AlertService: drug_interactions collection is empty; "
                "using built-in fallback (%d interactions)",
                len(self._interactions_cache),
            )

    async def reload_interactions(self) -> None:
        """Hot-reload drug interactions from MongoDB without restarting the service (REQ 12.3)."""
        await self.load_interactions_from_db()

    async def check_prescription(
        self,
        prescription: Prescription,
        patient: PatientProfile,
    ) -> list[SafetyAlert]:
        """Verify allergies, drug interactions, and contraindications.

        Returns a list of SafetyAlert objects. Critical alerts indicate
        blocking issues; warning alerts are informational.
        """
        alerts: list[SafetyAlert] = []

        alerts.extend(self._check_allergies(prescription, patient))
        alerts.extend(self._check_interactions(prescription, patient))
        alerts.extend(self._check_age_contraindications(prescription, patient))
        alerts.extend(self._check_organ_failure(prescription, patient))

        return alerts

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_allergies(
        self,
        prescription: Prescription,
        patient: PatientProfile,
    ) -> list[SafetyAlert]:
        """Generate a CRITICAL alert if the prescribed antibiotic matches a known allergy."""
        alerts: list[SafetyAlert] = []
        drug_lower = prescription.antibiotic.lower()

        for allergy in patient.allergies:
            allergy_lower = allergy.lower()
            # Match if the allergy string contains the drug name or vice-versa
            if allergy_lower in drug_lower or drug_lower in allergy_lower:
                protocol = ANTIBIOTIC_PROTOCOLS.get(drug_lower)
                alternative = protocol.alternative if protocol else None

                alerts.append(
                    SafetyAlert(
                        level=AlertLevel.CRITICAL,
                        type="allergy",
                        message=(
                            f"Allergie connue à {prescription.antibiotic!r} détectée "
                            f"pour ce patient. Prescription bloquée."
                        ),
                        affected_drug=prescription.antibiotic,
                        alternative=alternative,
                    )
                )
                break  # one allergy alert per drug is sufficient

        return alerts

    def _check_interactions(
        self,
        prescription: Prescription,
        patient: PatientProfile,
    ) -> list[SafetyAlert]:
        """Generate WARNING alerts for known drug interactions with current medications.

        Checks symmetrically: (A prescribed, B in medications) == (B prescribed, A in medications)
        (REQ 12.4).
        """
        alerts: list[SafetyAlert] = []
        drug_lower = prescription.antibiotic.lower()

        for med in patient.current_medications:
            med_lower = med.lower()
            for drug_a, drug_b, message in self._interactions_cache:
                # Symmetric check: match regardless of which is drug_a or drug_b
                if (drug_lower == drug_a and drug_b in med_lower) or (
                    drug_lower == drug_b and drug_a in med_lower
                ):
                    alerts.append(
                        SafetyAlert(
                            level=AlertLevel.WARNING,
                            type="interaction",
                            message=message,
                            affected_drug=prescription.antibiotic,
                        )
                    )

        return alerts

    def _check_age_contraindications(
        self,
        prescription: Prescription,
        patient: PatientProfile,
    ) -> list[SafetyAlert]:
        """Generate CRITICAL alerts for age-based contraindications."""
        alerts: list[SafetyAlert] = []
        drug_lower = prescription.antibiotic.lower()
        protocol = ANTIBIOTIC_PROTOCOLS.get(drug_lower)

        if protocol is None or not protocol.contraindicated_age_groups:
            return alerts

        age_group = patient.age_group
        if age_group in protocol.contraindicated_age_groups:
            alerts.append(
                SafetyAlert(
                    level=AlertLevel.CRITICAL,
                    type="contraindication",
                    message=(
                        f"{prescription.antibiotic!r} est contre-indiqué pour le groupe "
                        f"d'âge {age_group.value!r}."
                    ),
                    affected_drug=prescription.antibiotic,
                    alternative=protocol.alternative,
                )
            )

        return alerts

    def _check_organ_failure(
        self,
        prescription: Prescription,
        patient: PatientProfile,
    ) -> list[SafetyAlert]:
        """Generate WARNING alerts when organ failure requires dose adjustment."""
        alerts: list[SafetyAlert] = []
        drug_lower = prescription.antibiotic.lower()
        protocol = ANTIBIOTIC_PROTOCOLS.get(drug_lower)

        if protocol is None:
            return alerts

        renal_failure = (
            patient.comorbidities.renal_failure if patient.comorbidities else False
        )
        hepatic_failure = (
            patient.comorbidities.hepatic_failure if patient.comorbidities else False
        )

        if renal_failure and protocol.renal_adjustment_factor < 1.0:
            alerts.append(
                SafetyAlert(
                    level=AlertLevel.WARNING,
                    type="contraindication",
                    message=(
                        f"Insuffisance rénale détectée : dose de {prescription.antibiotic!r} "
                        f"réduite à {int(protocol.renal_adjustment_factor * 100)}% de la dose standard."
                    ),
                    affected_drug=prescription.antibiotic,
                )
            )

        if hepatic_failure and protocol.hepatic_adjustment_factor < 1.0:
            alerts.append(
                SafetyAlert(
                    level=AlertLevel.WARNING,
                    type="contraindication",
                    message=(
                        f"Insuffisance hépatique détectée : dose de {prescription.antibiotic!r} "
                        f"réduite à {int(protocol.hepatic_adjustment_factor * 100)}% de la dose standard."
                    ),
                    affected_drug=prescription.antibiotic,
                )
            )

        return alerts


# Module-level singleton
alert_service = AlertService()
