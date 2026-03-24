"""
AlertService — safety alert checking for antibiotic prescriptions (REQ-09).

Checks:
- Known patient allergies (critical)
- Drug interactions with current medications (warning)
- Age-based contraindications (critical)
- Organ failure contraindications (warning)
"""
from __future__ import annotations

from backend.models.alert import SafetyAlert
from backend.models.common import AgeGroup, AlertLevel
from backend.models.consultation import Prescription
from backend.models.patient import PatientProfile
from backend.services.prescription_service import ANTIBIOTIC_PROTOCOLS

# ---------------------------------------------------------------------------
# Known drug interaction pairs (symmetric)
# Each entry: (drug_a_lower, drug_b_lower) → warning message
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
        """Generate WARNING alerts for known drug interactions with current medications."""
        alerts: list[SafetyAlert] = []
        drug_lower = prescription.antibiotic.lower()

        for med in patient.current_medications:
            med_lower = med.lower()
            for drug_a, drug_b, message in _DRUG_INTERACTIONS:
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
