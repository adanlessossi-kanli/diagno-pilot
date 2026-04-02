from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fastapi import HTTPException

from backend.models.common import AgeGroup
from backend.models.consultation import LocalisedPrescription
from backend.services.audit_service import audit_service

logger = logging.getLogger(__name__)


@dataclass
class AntibioticProtocol:
    name: str
    paediatric_dose_per_kg: float
    adult_max_dose_mg: float
    frequency: str
    duration_days: int
    route: str
    renal_adjustment_factor: float = 1.0
    hepatic_adjustment_factor: float = 1.0
    contraindicated_age_groups: list = field(default_factory=list)
    alternative: str | None = None
    region: str = "ALL"
    available_regions: list = field(default_factory=lambda: ["TG", "BJ"])
    atc_class: str = ""
    first_line: bool = True
    names: dict = field(default_factory=dict)
    version: str = ""
    created_at: str = ""


ANTIBIOTIC_PROTOCOLS = {
    "amoxicillin": AntibioticProtocol(
        name="amoxicillin", paediatric_dose_per_kg=50.0, adult_max_dose_mg=3000.0,
        frequency="3x/day", duration_days=7, route="oral",
        renal_adjustment_factor=0.5, atc_class="J01CA04",
    ),
    "amoxicillin-clavulanate": AntibioticProtocol(
        name="amoxicillin-clavulanate", paediatric_dose_per_kg=45.0, adult_max_dose_mg=2625.0,
        frequency="3x/day", duration_days=7, route="oral",
        renal_adjustment_factor=0.5, atc_class="J01CR02",
    ),
    "ceftriaxone": AntibioticProtocol(
        name="ceftriaxone", paediatric_dose_per_kg=50.0, adult_max_dose_mg=2000.0,
        frequency="1x/day", duration_days=7, route="IV",
        renal_adjustment_factor=0.75, atc_class="J01DD04",
    ),
    "ciprofloxacin": AntibioticProtocol(
        name="ciprofloxacin", paediatric_dose_per_kg=20.0, adult_max_dose_mg=1500.0,
        frequency="2x/day", duration_days=7, route="oral",
        renal_adjustment_factor=0.5,
        contraindicated_age_groups=[AgeGroup.NEONATAL, AgeGroup.INFANT, AgeGroup.CHILD],
        alternative="ceftriaxone", atc_class="J01MA02",
    ),
    "metronidazole": AntibioticProtocol(
        name="metronidazole", paediatric_dose_per_kg=30.0, adult_max_dose_mg=2000.0,
        frequency="3x/day", duration_days=7, route="oral",
        hepatic_adjustment_factor=0.5, atc_class="J01XD01",
    ),
    "azithromycin": AntibioticProtocol(
        name="azithromycin", paediatric_dose_per_kg=10.0, adult_max_dose_mg=500.0,
        frequency="1x/day", duration_days=5, route="oral",
        hepatic_adjustment_factor=0.75, atc_class="J01FA10",
    ),
    "doxycycline": AntibioticProtocol(
        name="doxycycline", paediatric_dose_per_kg=4.0, adult_max_dose_mg=200.0,
        frequency="2x/day", duration_days=7, route="oral",
        contraindicated_age_groups=[AgeGroup.NEONATAL, AgeGroup.INFANT, AgeGroup.CHILD],
        alternative="azithromycin", atc_class="J01AA02",
    ),
    "cotrimoxazole": AntibioticProtocol(
        name="cotrimoxazole", paediatric_dose_per_kg=48.0, adult_max_dose_mg=1920.0,
        frequency="2x/day", duration_days=5, route="oral",
        renal_adjustment_factor=0.5, atc_class="J01EE01",
    ),
    "gentamicin": AntibioticProtocol(
        name="gentamicin", paediatric_dose_per_kg=5.0, adult_max_dose_mg=240.0,
        frequency="1x/day", duration_days=7, route="IV",
        renal_adjustment_factor=0.25, atc_class="J01GB03",
    ),
    "penicillin-v": AntibioticProtocol(
        name="penicillin-v", paediatric_dose_per_kg=50.0, adult_max_dose_mg=2000.0,
        frequency="4x/day", duration_days=10, route="oral",
        renal_adjustment_factor=0.5, atc_class="J01CE02",
    ),
}

_PAEDIATRIC_GROUPS = {AgeGroup.NEONATAL, AgeGroup.INFANT, AgeGroup.CHILD}


def _doc_to_protocol(doc):
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
        region=doc.get("region", "ALL"),
        available_regions=doc.get("available_regions", ["TG", "BJ"]),
        atc_class=doc.get("atc_class", ""),
        first_line=bool(doc.get("first_line", True)),
        names=doc.get("names", {}),
        version=doc.get("version", ""),
        created_at=doc.get("created_at", ""),
    )


def _resolve_display_name(protocol, locale):
    if not protocol.names:
        return protocol.name
    candidates = [locale]
    if "-" in locale:
        candidates.append(locale.split("-")[0])
    candidates.extend(["fr", "en"])
    for candidate in candidates:
        if candidate in protocol.names:
            return protocol.names[candidate]
    return protocol.name


class PrescriptionService:
    def __init__(self):
        self._protocols_cache = {}

    async def load_protocols_from_db(self):
        from backend.core.database import db
        from backend.core.db_metrics import timed_db_op
        try:
            database = db.get_db()
            async with timed_db_op("antibiotic_protocols", "find"):
                cursor = database["antibiotic_protocols"].find({})
                docs = await cursor.to_list(length=None)
        except Exception:
            import logging as _l
            _l.getLogger(__name__).warning("Failed to load protocols from MongoDB; using built-in fallback", exc_info=True)
            docs = []
        if docs:
            new_cache = {}
            for doc in docs:
                protocol = _doc_to_protocol(doc)
                key = (protocol.name.lower(), protocol.region)
                existing = new_cache.get(key)
                if existing is None or protocol.created_at >= existing.created_at:
                    new_cache[key] = protocol
            self._protocols_cache = new_cache
            from backend.core.cache import cache_service
            from backend.core.config import settings as _settings
            for (name, region), protocol in self._protocols_cache.items():
                cache_key = cache_service.make_key("protocol", f"{name}:{region}")
                await cache_service.set(cache_key, __import__("json").dumps(__import__("dataclasses").asdict(protocol)), ttl=_settings.CACHE_TTL_PROTOCOLS)
        else:
            self._protocols_cache = {(name, "ALL"): protocol for name, protocol in ANTIBIOTIC_PROTOCOLS.items()}

    async def reload_protocols(self, name=None):
        from backend.core.cache import cache_service
        if name is not None:
            for region in ("TG", "BJ", "ALL"):
                key = cache_service.make_key("protocol", f"{name.lower()}:{region}")
                await cache_service.delete(key)
        else:
            pattern = cache_service.make_key("protocol", "*")
            await cache_service.flush_pattern(pattern)
        await self.load_protocols_from_db()

    async def _get_protocol(self, name, region="ALL"):
        from backend.core.cache import cache_service
        async def _try_tier(n, r):
            cache_key = cache_service.make_key("protocol", f"{n}:{r}")
            raw = await cache_service.get(cache_key)
            if raw is not None:
                try:
                    return _doc_to_protocol(__import__("json").loads(raw))
                except Exception:
                    pass
            return self._protocols_cache.get((n, r))
        if region != "ALL":
            protocol = await _try_tier(name, region)
            if protocol is not None:
                return protocol
        protocol = await _try_tier(name, "ALL")
        if protocol is not None:
            return protocol
        protocol = ANTIBIOTIC_PROTOCOLS.get(name)
        if protocol is not None:
            return protocol
        raise HTTPException(status_code=422, detail="unknown_antibiotic")

    def _find_alternative(self, atc_class, first_line, region, exclude_name):
        candidates = []
        seen = set()
        for protocol in self._protocols_cache.values():
            if protocol.name.lower() != exclude_name and protocol.name not in seen:
                candidates.append(protocol)
                seen.add(protocol.name)
        for name, protocol in ANTIBIOTIC_PROTOCOLS.items():
            if name != exclude_name and name not in seen:
                candidates.append(protocol)
                seen.add(name)
        def _available(p):
            return region == "ALL" or region in p.available_regions
        for p in candidates:
            if p.atc_class == atc_class and p.first_line == first_line and _available(p):
                return p
        for p in candidates:
            if p.atc_class == atc_class and _available(p):
                return p
        return None

    async def _get_drug_catalogue_entry(self, inn):
        try:
            from backend.core.database import db
            database = db.get_db()
            doc = await database["drug_catalogue"].find_one({"inn": inn.lower()})
            return doc
        except Exception:
            return None

    async def calculate_prescription(self, antibiotic, patient, locale="fr-TG", region="ALL"):
        key = antibiotic.lower()
        protocol = await self._get_protocol(key, region)
        unavailable_in_region = False
        if region != "ALL" and region not in protocol.available_regions:
            unavailable_in_region = True
            alternative = self._find_alternative(
                atc_class=protocol.atc_class, first_line=protocol.first_line,
                region=region, exclude_name=key,
            )
            if alternative is not None:
                protocol = alternative
        age_group = patient.age_group
        is_paediatric = age_group in _PAEDIATRIC_GROUPS
        is_capped = False
        dose_per_kg = None
        if is_paediatric:
            weight = patient.weight_kg
            if weight is None or weight <= 0:
                raise ValueError("weight_kg must be a positive number for paediatric dose calculation")
            raw_dose = protocol.paediatric_dose_per_kg * weight
            dose_per_kg = protocol.paediatric_dose_per_kg
            if raw_dose > protocol.adult_max_dose_mg:
                dose_mg = protocol.adult_max_dose_mg
                is_capped = True
            else:
                dose_mg = raw_dose
        else:
            dose_mg = protocol.adult_max_dose_mg
        renal_failure = patient.comorbidities.renal_failure if patient.comorbidities else False
        hepatic_failure = patient.comorbidities.hepatic_failure if patient.comorbidities else False
        if renal_failure:
            dose_mg *= protocol.renal_adjustment_factor
        if hepatic_failure:
            dose_mg *= protocol.hepatic_adjustment_factor
        dose_mg = max(dose_mg, 0.0)
        display_name = _resolve_display_name(protocol, locale)
        trade_name = None
        catalogue_doc = await self._get_drug_catalogue_entry(protocol.name)
        if catalogue_doc is not None:
            trade_names = catalogue_doc.get("trade_names", {})
            trade_name = trade_names.get(region) or None
        result = LocalisedPrescription(
            antibiotic=protocol.name,
            dose_mg=round(dose_mg, 2),
            dose_per_kg=dose_per_kg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
            is_capped_to_adult_dose=is_capped,
            display_name=display_name,
            trade_name=trade_name,
            unavailable_in_region=unavailable_in_region,
            protocol_version=protocol.version,
            locale=locale,
            region=region,
        )
        try:
            await audit_service.log_action(
                user_id="system",
                action="create_prescription",
                resource="prescriptions",
                details={
                    "antibiotic": protocol.name,
                    "protocol_version": protocol.version,
                },
                locale=locale,
                region=region,
            )
        except Exception:
            logger.warning("Failed to write prescription audit log", exc_info=True)
        return result


prescription_service = PrescriptionService()
