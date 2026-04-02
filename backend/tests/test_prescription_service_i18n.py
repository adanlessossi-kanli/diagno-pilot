"""
Property-based and integration tests for PrescriptionService i18n/region features.

Tasks 6.5–6.9 — i18n-medical-content spec
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.models.common import AgeGroup
from backend.models.patient import Comorbidities, PatientProfile
from backend.services.prescription_service import (
    ANTIBIOTIC_PROTOCOLS,
    AntibioticProtocol,
    PrescriptionService,
)

# ---------------------------------------------------------------------------
# Hypothesis profile
# ---------------------------------------------------------------------------

settings.register_profile("ci", max_examples=100, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("ci")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adult(weight_kg: float = 70.0) -> PatientProfile:
    return PatientProfile(
        full_name="Test Patient",
        weight_kg=weight_kg,
        age_group=AgeGroup.ADULT,
        allergies=[],
        comorbidities=Comorbidities(),
    )


def _make_protocol(name: str, adult_max_dose_mg: float, atc_class: str = "J01CA04",
                   available_regions: list | None = None, first_line: bool = True,
                   names: dict | None = None, region: str = "ALL") -> AntibioticProtocol:
    return AntibioticProtocol(
        name=name,
        paediatric_dose_per_kg=50.0,
        adult_max_dose_mg=adult_max_dose_mg,
        frequency="3x/day",
        duration_days=7,
        route="oral",
        atc_class=atc_class,
        first_line=first_line,
        available_regions=available_regions if available_regions is not None else ["TG", "BJ"],
        names=names or {},
        region=region,
    )


def _make_svc_with_cache(cache_entries: dict) -> PrescriptionService:
    """Create a PrescriptionService with pre-populated cache and mocked cache_service."""
    svc = PrescriptionService()
    svc._protocols_cache = cache_entries
    return svc


def _run_calculate(svc: PrescriptionService, antibiotic: str, patient: PatientProfile,
                   locale: str = "fr-TG", region: str = "ALL"):
    """Run calculate_prescription with mocked cache_service (always cache-miss)."""
    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.make_key = MagicMock(return_value="mock-key")

    with patch("backend.core.cache.cache_service", mock_cache):
        return asyncio.run(svc.calculate_prescription(antibiotic, patient, locale=locale, region=region))


# ---------------------------------------------------------------------------
# Property 5: region-aware protocol lookup priority
# Feature: i18n-medical-content, Property 5: region-aware protocol lookup priority
# ---------------------------------------------------------------------------

class TestProperty5RegionAwareLookupPriority:
    """
    **Validates: Requirements 2.2, 2.3**

    For any antibiotic name and region R ∈ {"TG", "BJ"}, when both a
    region-specific variant (name, R) and a universal variant (name, "ALL")
    exist in the protocol cache, _get_protocol() SHALL return the
    region-specific variant. When only the ALL variant exists, it SHALL
    return the ALL variant.
    """

    @given(
        name=st.sampled_from(sorted(ANTIBIOTIC_PROTOCOLS.keys())),
        region=st.sampled_from(["TG", "BJ"]),
        region_dose=st.floats(min_value=100.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
        all_dose=st.floats(min_value=100.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    )
    def test_region_specific_takes_priority_over_all(
        self, name: str, region: str, region_dose: float, all_dose: float
    ):
        # Ensure doses are distinguishable
        if abs(region_dose - all_dose) < 1.0:
            all_dose = region_dose + 200.0

        region_protocol = _make_protocol(name, region_dose, region=region)
        all_protocol = _make_protocol(name, all_dose, region="ALL")

        svc = _make_svc_with_cache({
            (name, region): region_protocol,
            (name, "ALL"): all_protocol,
        })

        mock_cache = MagicMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.make_key = MagicMock(return_value="mock-key")

        with patch("backend.core.cache.cache_service", mock_cache):
            result = asyncio.run(svc._get_protocol(name, region))

        assert result.adult_max_dose_mg == pytest.approx(region_dose), (
            f"Expected region-specific dose {region_dose} but got {result.adult_max_dose_mg}"
        )

    @given(
        name=st.sampled_from(sorted(ANTIBIOTIC_PROTOCOLS.keys())),
        region=st.sampled_from(["TG", "BJ"]),
        all_dose=st.floats(min_value=100.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    )
    def test_all_variant_returned_when_no_region_specific(
        self, name: str, region: str, all_dose: float
    ):
        all_protocol = _make_protocol(name, all_dose, region="ALL")

        svc = _make_svc_with_cache({(name, "ALL"): all_protocol})

        mock_cache = MagicMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.make_key = MagicMock(return_value="mock-key")

        with patch("backend.core.cache.cache_service", mock_cache):
            result = asyncio.run(svc._get_protocol(name, region))

        assert result.adult_max_dose_mg == pytest.approx(all_dose)


# ---------------------------------------------------------------------------
# Property 6: unavailable protocol triggers alternative suggestion
# Feature: i18n-medical-content, Property 6: unavailable protocol triggers alternative suggestion
# ---------------------------------------------------------------------------

class TestProperty6UnavailableProtocolAlternative:
    """
    **Validates: Requirements 2.6, 3.5**

    For any antibiotic protocol whose available_regions list does not include
    the request region, calculate_prescription() SHALL NOT return that protocol
    as the primary prescription and SHALL include an alternative from the same
    ATC class (unavailable_in_region=True).
    """

    @given(region=st.sampled_from(["TG", "BJ"]))
    def test_unavailable_triggers_alternative(self, region: str):
        other_region = "BJ" if region == "TG" else "TG"
        atc = "J01CA04"

        # Primary: unavailable in the requested region
        primary = _make_protocol(
            "test-primary", adult_max_dose_mg=1000.0, atc_class=atc,
            available_regions=[other_region], first_line=True,
        )
        # Alternative: available in the requested region
        alternative = _make_protocol(
            "test-alternative", adult_max_dose_mg=2000.0, atc_class=atc,
            available_regions=[region, other_region], first_line=True,
        )

        svc = _make_svc_with_cache({
            ("test-primary", "ALL"): primary,
            ("test-alternative", "ALL"): alternative,
        })

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=None)):
            rx = _run_calculate(svc, "test-primary", _adult(), locale=f"fr-{region}", region=region)

        assert rx.unavailable_in_region is True
        assert rx.antibiotic != "test-primary", (
            "Should have switched to alternative, not returned unavailable primary"
        )
        assert rx.antibiotic == "test-alternative"

    @given(region=st.sampled_from(["TG", "BJ"]))
    def test_unavailable_no_alternative_still_flags(self, region: str):
        other_region = "BJ" if region == "TG" else "TG"
        atc = "J01ZZ99"  # unique ATC class with no alternative

        primary = _make_protocol(
            "test-only-drug", adult_max_dose_mg=1000.0, atc_class=atc,
            available_regions=[other_region],
        )

        svc = _make_svc_with_cache({("test-only-drug", "ALL"): primary})

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=None)):
            rx = _run_calculate(svc, "test-only-drug", _adult(), locale=f"fr-{region}", region=region)

        assert rx.unavailable_in_region is True


# ---------------------------------------------------------------------------
# Property 7: prescription display name always present
# Feature: i18n-medical-content, Property 7: prescription response always includes localised display name
# ---------------------------------------------------------------------------

class TestProperty7DisplayNameAlwaysPresent:
    """
    **Validates: Requirements 2.4, 2.5, 9.5**

    For any prescription response and any supported locale, the display_name
    field SHALL be a non-empty string.
    """

    @given(
        locale=st.sampled_from(["fr-TG", "fr-BJ", "en", "fr"]),
        antibiotic=st.sampled_from(sorted(ANTIBIOTIC_PROTOCOLS.keys())),
    )
    def test_display_name_non_empty_with_names_map(self, locale: str, antibiotic: str):
        names = {"fr": "Amoxicilline", "en": "Amoxicillin", "fr-TG": "Amoxicilline-TG"}
        protocol = _make_protocol(antibiotic, adult_max_dose_mg=1000.0, names=names)

        svc = _make_svc_with_cache({(antibiotic, "ALL"): protocol})

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=None)):
            rx = _run_calculate(svc, antibiotic, _adult(), locale=locale)

        assert rx.display_name, f"display_name must be non-empty for locale={locale}"
        assert isinstance(rx.display_name, str)

    @given(
        locale=st.sampled_from(["fr-TG", "fr-BJ", "en", "fr"]),
        antibiotic=st.sampled_from(sorted(ANTIBIOTIC_PROTOCOLS.keys())),
    )
    def test_display_name_non_empty_without_names_map(self, locale: str, antibiotic: str):
        # Legacy protocol with empty names dict
        protocol = _make_protocol(antibiotic, adult_max_dose_mg=1000.0, names={})

        svc = _make_svc_with_cache({(antibiotic, "ALL"): protocol})

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=None)):
            rx = _run_calculate(svc, antibiotic, _adult(), locale=locale)

        assert rx.display_name, f"display_name must be non-empty for locale={locale} (legacy protocol)"
        assert isinstance(rx.display_name, str)
        # Legacy fallback: display_name should equal the protocol name
        assert rx.display_name == antibiotic


# ---------------------------------------------------------------------------
# Property 8: INN always present, trade name conditional
# Feature: i18n-medical-content, Property 8: drug catalogue response includes INN and conditional trade name
# ---------------------------------------------------------------------------

class TestProperty8INNAndTradeNameConditional:
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    For any prescription response:
    - The antibiotic field (INN) SHALL always be present and non-empty.
    - When the drug catalogue contains a trade name for the request region,
      trade_name SHALL be non-null.
    - When no trade name exists for the region, trade_name SHALL be None.
    """

    @given(
        region=st.sampled_from(["TG", "BJ", "ALL"]),
        has_trade_name=st.booleans(),
    )
    def test_inn_always_present_and_trade_name_conditional(
        self, region: str, has_trade_name: bool
    ):
        antibiotic = "amoxicillin"
        protocol = _make_protocol(antibiotic, adult_max_dose_mg=1000.0)
        svc = _make_svc_with_cache({(antibiotic, "ALL"): protocol})

        if has_trade_name:
            catalogue_doc = {"inn": antibiotic, "trade_names": {region: "Amoxil-Brand"}}
        else:
            catalogue_doc = None

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=catalogue_doc)):
            rx = _run_calculate(svc, antibiotic, _adult(), locale="fr-TG", region=region)

        # INN always present
        assert rx.antibiotic, "antibiotic (INN) must always be non-empty"
        assert isinstance(rx.antibiotic, str)

        # Trade name conditional
        if has_trade_name:
            assert rx.trade_name == "Amoxil-Brand", (
                f"Expected trade name 'Amoxil-Brand' for region={region}"
            )
        else:
            assert rx.trade_name is None, (
                f"Expected trade_name=None when no catalogue doc, got {rx.trade_name!r}"
            )


# ---------------------------------------------------------------------------
# Task 6.9 — Integration unit tests
# ---------------------------------------------------------------------------

class TestLocalisedPrescriptionIntegration:

    def test_localised_prescription_tg_region(self):
        """TG request with names map → display_name='Amoxicilline', locale='fr-TG', region='TG'."""
        protocol = _make_protocol(
            "amoxicillin", adult_max_dose_mg=3000.0,
            names={"fr": "Amoxicilline", "en": "Amoxicillin"},
            available_regions=["TG", "BJ"],
        )
        svc = _make_svc_with_cache({("amoxicillin", "ALL"): protocol})

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=None)):
            rx = _run_calculate(svc, "amoxicillin", _adult(), locale="fr-TG", region="TG")

        assert rx.display_name == "Amoxicilline"
        assert rx.locale == "fr-TG"
        assert rx.region == "TG"
        assert rx.unavailable_in_region is False

    def test_localised_prescription_bj_region(self):
        """BJ request → locale='fr-BJ', region='BJ'."""
        protocol = _make_protocol(
            "amoxicillin", adult_max_dose_mg=3000.0,
            available_regions=["TG", "BJ"],
        )
        svc = _make_svc_with_cache({("amoxicillin", "ALL"): protocol})

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=None)):
            rx = _run_calculate(svc, "amoxicillin", _adult(), locale="fr-BJ", region="BJ")

        assert rx.locale == "fr-BJ"
        assert rx.region == "BJ"

    def test_localised_prescription_with_trade_name(self):
        """Mock drug catalogue returning trade name for TG → trade_name='Amoxil-TG'."""
        protocol = _make_protocol("amoxicillin", adult_max_dose_mg=3000.0)
        svc = _make_svc_with_cache({("amoxicillin", "ALL"): protocol})
        catalogue_doc = {"inn": "amoxicillin", "trade_names": {"TG": "Amoxil-TG"}}

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=catalogue_doc)):
            rx = _run_calculate(svc, "amoxicillin", _adult(), locale="fr-TG", region="TG")

        assert rx.trade_name == "Amoxil-TG"

    def test_localised_prescription_no_trade_name(self):
        """Mock drug catalogue returning None → trade_name=None."""
        protocol = _make_protocol("amoxicillin", adult_max_dose_mg=3000.0)
        svc = _make_svc_with_cache({("amoxicillin", "ALL"): protocol})

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=None)):
            rx = _run_calculate(svc, "amoxicillin", _adult(), locale="fr-TG", region="TG")

        assert rx.trade_name is None

    def test_localised_prescription_legacy_doc(self):
        """Protocol with empty names={} → display_name equals raw name."""
        protocol = _make_protocol("amoxicillin", adult_max_dose_mg=3000.0, names={})
        svc = _make_svc_with_cache({("amoxicillin", "ALL"): protocol})

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=None)):
            rx = _run_calculate(svc, "amoxicillin", _adult(), locale="fr-TG", region="TG")

        assert rx.display_name == "amoxicillin"

    def test_region_specific_protocol_takes_priority(self):
        """Cache has both (name, 'TG') and (name, 'ALL') → TG request uses TG variant dose."""
        tg_dose = 1500.0
        all_dose = 3000.0
        tg_protocol = _make_protocol("amoxicillin", adult_max_dose_mg=tg_dose, region="TG")
        all_protocol = _make_protocol("amoxicillin", adult_max_dose_mg=all_dose, region="ALL")

        svc = _make_svc_with_cache({
            ("amoxicillin", "TG"): tg_protocol,
            ("amoxicillin", "ALL"): all_protocol,
        })

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=None)):
            rx = _run_calculate(svc, "amoxicillin", _adult(), locale="fr-TG", region="TG")

        assert rx.dose_mg == pytest.approx(tg_dose), (
            f"Expected TG-specific dose {tg_dose}, got {rx.dose_mg}"
        )

    def test_all_fallback_when_no_region_specific(self):
        """Cache has only (name, 'ALL') → TG request falls back to ALL variant."""
        all_dose = 3000.0
        all_protocol = _make_protocol("amoxicillin", adult_max_dose_mg=all_dose, region="ALL")

        svc = _make_svc_with_cache({("amoxicillin", "ALL"): all_protocol})

        with patch.object(svc, "_get_drug_catalogue_entry", new=AsyncMock(return_value=None)):
            rx = _run_calculate(svc, "amoxicillin", _adult(), locale="fr-TG", region="TG")

        assert rx.dose_mg == pytest.approx(all_dose), (
            f"Expected ALL fallback dose {all_dose}, got {rx.dose_mg}"
        )
