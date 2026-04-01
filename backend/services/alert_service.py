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

import json
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
    """Safety alert checker for antibiotic prescriptions.

    Evaluates a prescription against a patient profile across four alert categories:

    1. **Allergy** (severity: ``critical``) — detects whether the prescribed antibiotic
       matches any of the patient's known allergies.
    2. **Drug interaction** (severity: ``warning``) — detects known interactions between
       the prescribed antibiotic and the patient's current medications.
    3. **Age contraindication** (severity: ``critical``) — detects antibiotics that are
       contraindicated for the patient's age group (e.g. fluoroquinolones in paediatric
       patients).
    4. **Organ failure** (severity: ``warning``) — detects when renal or hepatic
       impairment requires a dose reduction.

    Data sources:
    - Drug interaction pairs are loaded at startup from the MongoDB
      ``drug_interactions`` collection via :meth:`load_interactions_from_db`.
    - If the collection is empty or unreachable, the service falls back to the
      built-in :data:`_DRUG_INTERACTIONS` list defined in this module.
    - Antibiotic protocols (contraindicated age groups, adjustment factors) come
      from :data:`~backend.services.prescription_service.ANTIBIOTIC_PROTOCOLS`.
    """

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
            # Store full list in Redis cache
            from backend.core.cache import cache_service
            from backend.core.config import settings as _settings
            key = cache_service.make_key("drug_interactions", "all")
            await cache_service.set(
                key,
                json.dumps(list(self._interactions_cache)),
                ttl=_settings.CACHE_TTL_INTERACTIONS,
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
        from backend.core.cache import cache_service
        key = cache_service.make_key("drug_interactions", "all")
        await cache_service.delete(key)
        await self.load_interactions_from_db()

    async def _get_interactions(self) -> list[tuple[str, str, str]]:
        """Return the interaction list, checking Redis first then in-process cache.

        Lookup order:
            1. Redis cache — key ``v1:drug_interactions:all``
            2. In-process list (``self._interactions_cache``)
        """
        from backend.core.cache import cache_service
        cache_key = cache_service.make_key("drug_interactions", "all")
        raw = await cache_service.get(cache_key)
        if raw is not None:
            try:
                return [tuple(item) for item in json.loads(raw)]  # type: ignore[return-value]
            except Exception:
                pass  # fall through to in-process list
        return self._interactions_cache

    async def check_prescription(
        self,
        prescription: Prescription,
        patient: PatientProfile,
    ) -> list[SafetyAlert]:
        """Run all safety checks for a prescription and return any alerts.

        Checks are executed in the following order:

        1. :meth:`_check_allergies` — allergy match against the patient's known
           allergies.  Emits ``critical`` alerts that indicate the prescription
           should be blocked.
        2. :meth:`_check_interactions` — interaction match against the patient's
           current medications.  Emits ``warning`` alerts that are informational
           and do not automatically block the prescription.
        3. :meth:`_check_age_contraindications` — contraindication match against
           the patient's age group.  Emits ``critical`` alerts.
        4. :meth:`_check_organ_failure` — dose-adjustment check for renal or
           hepatic impairment.  Emits ``warning`` alerts.

        ``critical`` alerts signal that the prescription is clinically unsafe and
        should be blocked or require explicit override.  ``warning`` alerts flag
        conditions that require clinical attention but do not automatically prevent
        dispensing.

        Returns an empty list when no safety issues are detected.

        Args:
            prescription: The antibiotic prescription to evaluate.
            patient: The patient profile containing allergies, current medications,
                age group, and comorbidities.

        Returns:
            A (possibly empty) list of :class:`~backend.models.alert.SafetyAlert`
            objects ordered by check category.
        """
        alerts: list[SafetyAlert] = []

        interactions = await self._get_interactions()
        alerts.extend(self._check_allergies(prescription, patient))
        alerts.extend(self._check_interactions(prescription, patient, interactions))
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
        """Check whether the prescribed antibiotic matches a known patient allergy.

        Matching strategy: both the drug name and each allergy string are
        lower-cased, then a substring test is applied in both directions —
        i.e. an alert is raised if the allergy string is contained in the drug
        name *or* the drug name is contained in the allergy string.  This
        catches common variants such as ``"penicillin allergy"`` matching
        ``"amoxicillin"`` (which contains ``"cillin"``).

        Only one ``critical`` allergy alert is emitted per drug, regardless of
        how many allergy entries match.  This avoids duplicate alerts for the
        same clinical issue (e.g. a patient who has both ``"penicillin"`` and
        ``"amoxicillin"`` listed as allergies would still receive a single alert
        for a prescribed amoxicillin).

        Args:
            prescription: The antibiotic prescription to evaluate.
            patient: The patient profile whose ``allergies`` list is checked.

        Returns:
            A list containing at most one ``critical``
            :class:`~backend.models.alert.SafetyAlert` of type ``"allergy"``.
        """
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
        interactions: list[tuple[str, str, str]] | None = None,
    ) -> list[SafetyAlert]:
        """Check for known drug interactions between the prescription and current medications.

        Interaction data is sourced from :attr:`_interactions_cache`, which is
        populated at startup from the MongoDB ``drug_interactions`` collection
        (via :meth:`load_interactions_from_db`) or from the built-in
        :data:`_DRUG_INTERACTIONS` fallback list if the collection is unavailable.

        Matching is symmetric: an interaction pair ``(drug_a, drug_b)`` is
        triggered whether the prescribed antibiotic corresponds to ``drug_a``
        and the current medication to ``drug_b``, or vice versa.  This ensures
        that the order in which pairs are stored in the database does not affect
        detection.

        Each matching pair produces a separate ``warning``-level alert.  Multiple
        alerts may be returned if the patient is taking several interacting
        medications simultaneously.

        Args:
            prescription: The antibiotic prescription to evaluate.
            patient: The patient profile whose ``current_medications`` list is
                checked.

        Returns:
            A (possibly empty) list of ``warning``
            :class:`~backend.models.alert.SafetyAlert` objects of type
            ``"interaction"``.
        """
        alerts: list[SafetyAlert] = []
        drug_lower = prescription.antibiotic.lower()

        interaction_list = interactions if interactions is not None else self._interactions_cache
        for med in patient.current_medications:
            med_lower = med.lower()
            for drug_a, drug_b, message in interaction_list:
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
        """Check whether the prescribed antibiotic is contraindicated for the patient's age group.

        Paediatric age groups are defined as :attr:`AgeGroup.NEONATAL`,
        :attr:`AgeGroup.INFANT`, and :attr:`AgeGroup.CHILD` (collected in the
        module-level :data:`_PAEDIATRIC_GROUPS` set).  Adult and elderly patients
        are not considered paediatric and are therefore not subject to
        paediatric-specific contraindications.

        The check consults the ``contraindicated_age_groups`` field of the
        antibiotic's protocol entry in
        :data:`~backend.services.prescription_service.ANTIBIOTIC_PROTOCOLS`.
        If the patient's :attr:`~backend.models.patient.PatientProfile.age_group`
        is present in that set, a ``critical`` alert is raised.  No alert is
        emitted when the protocol has no contraindicated age groups or when the
        antibiotic is not found in the protocols dictionary.

        Args:
            prescription: The antibiotic prescription to evaluate.
            patient: The patient profile whose ``age_group`` is checked.

        Returns:
            A list containing at most one ``critical``
            :class:`~backend.models.alert.SafetyAlert` of type
            ``"contraindication"``.
        """
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
        """Check whether renal or hepatic impairment requires a dose adjustment.

        Two adjustment factors are read from the antibiotic's protocol entry in
        :data:`~backend.services.prescription_service.ANTIBIOTIC_PROTOCOLS`:

        - ``renal_adjustment_factor`` — multiplier applied to the standard dose
          when the patient has renal failure.  A value of ``1.0`` means no
          adjustment is needed; values below ``1.0`` indicate a dose reduction.
        - ``hepatic_adjustment_factor`` — equivalent multiplier for hepatic
          failure.

        An alert is only emitted when the relevant failure flag is ``True`` *and*
        the corresponding adjustment factor is strictly less than ``1.0``.  This
        avoids spurious alerts for drugs that do not require organ-specific dose
        changes.

        The alert level is ``warning`` rather than ``critical`` because organ
        failure does not absolutely contraindicate the drug — it requires a
        monitored dose reduction.  The prescriber retains clinical discretion,
        unlike allergy or age contraindications where the drug must be avoided
        entirely.

        Args:
            prescription: The antibiotic prescription to evaluate.
            patient: The patient profile whose ``comorbidities`` (renal/hepatic
                failure flags) are checked.

        Returns:
            A (possibly empty) list of ``warning``
            :class:`~backend.models.alert.SafetyAlert` objects of type
            ``"contraindication"``, one per applicable organ failure condition.
        """
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
