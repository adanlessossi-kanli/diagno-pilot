"""
PrescriptionService — antibiotic prescription calculation (REQ-03, REQ-08, REQ-11).

Handles:
- Weight-based dose calculation (mg/kg) for paediatric age groups
- Capping to adult maximum dose (is_capped_to_adult_dose)
- Automatic adjustments for renal / hepatic failure
- Loading protocols from MongoDB with fallback to built-in dict (REQ 11.4, 11.5)
"""
from __future__ import annotations

import dataclasses
import json
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

    Role in the antibiotic prescription workflow:
        This service is the single entry point for computing a patient-specific
        antibiotic dose.  It combines a dosing protocol (mg/kg rate, adult cap,
        route, frequency, duration) with patient-specific adjustments for organ
        failure to produce a ready-to-dispense ``Prescription``.

    Protocol loading strategy:
        On application startup ``load_protocols_from_db`` should be called to
        populate the in-memory cache from the MongoDB ``antibiotic_protocols``
        collection.  If that collection is empty or unreachable the service
        falls back to the built-in ``ANTIBIOTIC_PROTOCOLS`` dictionary so that
        the application remains functional without a database connection.

    Patient profile fields consumed:
        - ``age_group``   — determines whether paediatric (mg/kg) or adult
                            (fixed max dose) dosing is applied.
        - ``weight_kg``   — required for paediatric dose calculation; a
                            ``ValueError`` is raised if absent or non-positive.
        - ``comorbidities.renal_failure``   — triggers the protocol's
                            ``renal_adjustment_factor`` when ``True``.
        - ``comorbidities.hepatic_failure`` — triggers the protocol's
                            ``hepatic_adjustment_factor`` when ``True``.
    """

    def __init__(self) -> None:
        # In-memory cache: name → AntibioticProtocol (populated from DB or fallback)
        self._protocols_cache: dict[str, AntibioticProtocol] = {}

    async def load_protocols_from_db(self) -> None:
        """Load antibiotic protocols from MongoDB into the in-memory cache.

        MongoDB collection:
            ``antibiotic_protocols`` — each document must contain at minimum
            the fields ``name``, ``paediatric_dose_per_kg``,
            ``adult_max_dose_mg``, ``frequency``, ``duration_days``, and
            ``route``.  Optional fields (``renal_adjustment_factor``,
            ``hepatic_adjustment_factor``, ``contraindicated_age_groups``,
            ``alternative``) default to safe values when absent.

        Fallback behaviour:
            If the collection returns zero documents *or* the database is
            unreachable, the in-memory cache is populated from the built-in
            ``ANTIBIOTIC_PROTOCOLS`` dictionary and a ``WARNING`` is logged.
            The service therefore remains fully functional without a live
            database connection.

        When to call:
            This method should be called once during application startup (e.g.
            in the FastAPI ``lifespan`` handler) before any prescription
            requests are served.  It can also be called via ``reload_protocols``
            after an admin operation updates the ``antibiotic_protocols``
            collection.
        """
        from backend.core.database import db
        from backend.core.db_metrics import timed_db_op

        try:
            database = db.get_db()
            async with timed_db_op("antibiotic_protocols", "find"):
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
            # Store each protocol in Redis cache
            from backend.core.cache import cache_service
            from backend.core.config import settings as _settings
            for name, protocol in self._protocols_cache.items():
                key = cache_service.make_key("protocol", name)
                await cache_service.set(
                    key,
                    json.dumps(dataclasses.asdict(protocol)),
                    ttl=_settings.CACHE_TTL_PROTOCOLS,
                )
        else:
            self._protocols_cache = dict(ANTIBIOTIC_PROTOCOLS)
            logger.warning(
                "PrescriptionService: antibiotic_protocols collection is empty; "
                "using built-in fallback (%d protocols)",
                len(self._protocols_cache),
            )

    async def reload_protocols(self, name: str | None = None) -> None:
        """Refresh the in-memory cache from MongoDB.

        Called after each PUT/POST admin operation (REQ 11.4).
        If *name* is provided, only that protocol's cache key is invalidated.
        Otherwise all protocol:* keys are flushed before reloading.
        """
        from backend.core.cache import cache_service
        if name is not None:
            key = cache_service.make_key("protocol", name)
            await cache_service.delete(key)
        else:
            pattern = cache_service.make_key("protocol", "*")
            await cache_service.flush_pattern(pattern)
        await self.load_protocols_from_db()

    async def _get_protocol(self, key: str) -> AntibioticProtocol:
        """Look up an antibiotic protocol using a three-level cache strategy.

        Lookup order:
            1. **Redis cache** — checked first via ``CacheService.get()``.
            2. **In-memory cache** (``self._protocols_cache``) — populated at
               startup from MongoDB via ``load_protocols_from_db``.
            3. **Built-in dictionary** (``ANTIBIOTIC_PROTOCOLS``) — consulted
               only when the cache is empty or the key is absent, providing a
               safe fallback for the representative subset of protocols bundled
               with the application.

        Args:
            key: Lowercase antibiotic name (e.g. ``"amoxicillin"``).

        Returns:
            The matching ``AntibioticProtocol`` dataclass instance.

        Raises:
            HTTPException 422 (``unknown_antibiotic``): If the antibiotic name
                is not found in either the cache or the built-in dictionary.
        """
        # 1. Redis cache
        from backend.core.cache import cache_service
        cache_key = cache_service.make_key("protocol", key)
        raw = await cache_service.get(cache_key)
        if raw is not None:
            try:
                return _doc_to_protocol(json.loads(raw))
            except Exception:
                pass  # fall through to in-process dict

        # 2. DB cache (populated at startup or after reload)
        protocol = self._protocols_cache.get(key)
        if protocol is not None:
            return protocol
        # 3. Fallback to built-in dict (in case cache was never loaded)
        protocol = ANTIBIOTIC_PROTOCOLS.get(key)
        if protocol is not None:
            return protocol
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unknown_antibiotic",
        )

    async def calculate_prescription(
        self,
        antibiotic: str,
        patient: PatientProfile,
    ) -> Prescription:
        """Return a Prescription adapted to the patient's weight, age group,
        and comorbidities.

        Paediatric mg/kg calculation:
            When ``patient.age_group`` is one of ``NEONATAL``, ``INFANT``, or
            ``CHILD``, the daily dose is computed as::

                dose_mg = protocol.paediatric_dose_per_kg × patient.weight_kg

            ``patient.weight_kg`` must be a positive number; a ``ValueError``
            is raised otherwise.

        Adult-dose cap (``is_capped_to_adult_dose``):
            If the weight-based paediatric dose exceeds
            ``protocol.adult_max_dose_mg``, the dose is clamped to that
            maximum and ``Prescription.is_capped_to_adult_dose`` is set to
            ``True``.  For adult patients the adult max dose is used directly
            without a weight calculation.

        Renal adjustment:
            When ``patient.comorbidities.renal_failure`` is ``True``, the
            computed dose is multiplied by
            ``protocol.renal_adjustment_factor`` (a value in ``(0, 1]``).

        Hepatic adjustment:
            When ``patient.comorbidities.hepatic_failure`` is ``True``, the
            computed dose is multiplied by
            ``protocol.hepatic_adjustment_factor`` (a value in ``(0, 1]``).
            Both adjustments are applied independently and cumulatively.

        Args:
            antibiotic: Antibiotic name (case-insensitive key).
            patient: Patient profile with weight, age group, and comorbidities.

        Returns:
            A Prescription with dose_mg, dose_per_kg (if paediatric),
            is_capped_to_adult_dose, frequency, duration_days, and route.

        Raises:
            HTTPException 422 (``unknown_antibiotic``): If the antibiotic name
                is not found in the protocol cache or built-in dictionary.
            ValueError: If ``patient.weight_kg`` is ``None`` or non-positive
                for a paediatric patient.
        """
        key = antibiotic.lower()
        protocol = await self._get_protocol(key)

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
