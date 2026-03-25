"""
Tests for AlertService — REQ 12 (drug interactions from MongoDB).

Covers:
- load_interactions_from_db() loads from MongoDB (REQ 12.1)
- Fallback to hardcoded _DRUG_INTERACTIONS when collection is empty (REQ 12.5)
- reload_interactions() hot-reload (REQ 12.3)
- Symmetry of interaction checks: A→B == B→A (REQ 12.4)

Property 15 (Hypothesis): Symmetry of drug interactions.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from backend.models.common import AlertLevel
from backend.models.consultation import Prescription
from backend.models.patient import PatientProfile
from backend.services.alert_service import AlertService, _DRUG_INTERACTIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prescription(antibiotic: str) -> Prescription:
    return Prescription(antibiotic=antibiotic, dose_mg=500.0, frequency="BID", duration_days=7, route="oral")


def _make_patient(medications: list[str]) -> PatientProfile:
    return PatientProfile(
        full_name="Test Patient",
        age_group=None,
        allergies=[],
        current_medications=medications,
    )


# ---------------------------------------------------------------------------
# Unit tests — load_interactions_from_db
# ---------------------------------------------------------------------------

class TestLoadInteractionsFromDb:
    @pytest.mark.asyncio
    async def test_loads_interactions_from_mongodb(self):
        """REQ 12.1 — interactions are loaded from MongoDB at startup."""
        service = AlertService()

        mock_docs = [
            {"drug_a": "amoxicillin", "drug_b": "warfarin", "message": "Interaction test"},
        ]
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_docs)
        mock_db.__getitem__ = MagicMock(return_value=MagicMock(find=MagicMock(return_value=mock_cursor)))

        with patch("backend.core.database.db") as mock_db_module:
            mock_db_module.get_db.return_value = mock_db
            await service.load_interactions_from_db()

        assert len(service._interactions_cache) == 1
        assert service._interactions_cache[0] == ("amoxicillin", "warfarin", "Interaction test")

    @pytest.mark.asyncio
    async def test_fallback_to_hardcoded_when_collection_empty(self):
        """REQ 12.5 — fallback to built-in interactions when collection is empty."""
        service = AlertService()

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.__getitem__ = MagicMock(return_value=MagicMock(find=MagicMock(return_value=mock_cursor)))

        with patch("backend.core.database.db") as mock_db_module:
            mock_db_module.get_db.return_value = mock_db
            await service.load_interactions_from_db()

        assert service._interactions_cache == list(_DRUG_INTERACTIONS)

    @pytest.mark.asyncio
    async def test_fallback_on_db_exception(self):
        """REQ 12.5 — fallback to built-in interactions when DB raises an exception."""
        service = AlertService()

        with patch("backend.core.database.db") as mock_db_module:
            mock_db_module.get_db.side_effect = RuntimeError("DB not connected")
            await service.load_interactions_from_db()

        assert service._interactions_cache == list(_DRUG_INTERACTIONS)

    @pytest.mark.asyncio
    async def test_drug_names_lowercased_on_load(self):
        """Drug names from DB are stored in lowercase."""
        service = AlertService()

        mock_docs = [
            {"drug_a": "Amoxicillin", "drug_b": "WARFARIN", "message": "Test"},
        ]
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_docs)
        mock_db.__getitem__ = MagicMock(return_value=MagicMock(find=MagicMock(return_value=mock_cursor)))

        with patch("backend.core.database.db") as mock_db_module:
            mock_db_module.get_db.return_value = mock_db
            await service.load_interactions_from_db()

        assert service._interactions_cache[0][0] == "amoxicillin"
        assert service._interactions_cache[0][1] == "warfarin"


# ---------------------------------------------------------------------------
# Unit tests — reload_interactions (hot-reload)
# ---------------------------------------------------------------------------

class TestReloadInteractions:
    @pytest.mark.asyncio
    async def test_reload_updates_cache(self):
        """REQ 12.3 — reload_interactions() updates the in-memory cache."""
        service = AlertService()
        original_count = len(service._interactions_cache)

        new_docs = [
            {"drug_a": "drug_x", "drug_b": "drug_y", "message": "New interaction"},
            {"drug_a": "drug_p", "drug_b": "drug_q", "message": "Another interaction"},
        ]
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=new_docs)
        mock_db.__getitem__ = MagicMock(return_value=MagicMock(find=MagicMock(return_value=mock_cursor)))

        with patch("backend.core.database.db") as mock_db_module:
            mock_db_module.get_db.return_value = mock_db
            await service.reload_interactions()

        assert len(service._interactions_cache) == 2
        assert service._interactions_cache[0] == ("drug_x", "drug_y", "New interaction")


# ---------------------------------------------------------------------------
# Unit tests — symmetry of _check_interactions
# ---------------------------------------------------------------------------

class TestInteractionSymmetry:
    @pytest.mark.asyncio
    async def test_interaction_detected_in_both_directions(self):
        """REQ 12.4 — A→B and B→A produce the same alert."""
        service = AlertService()
        # Use a known hardcoded interaction: ciprofloxacin + warfarin
        prescription_a = _make_prescription("ciprofloxacin")
        patient_with_warfarin = _make_patient(["warfarin"])

        prescription_b = _make_prescription("warfarin")
        patient_with_cipro = _make_patient(["ciprofloxacin"])

        alerts_ab = await service.check_prescription(prescription_a, patient_with_warfarin)
        alerts_ba = await service.check_prescription(prescription_b, patient_with_cipro)

        interaction_alerts_ab = [a for a in alerts_ab if a.type == "interaction"]
        interaction_alerts_ba = [a for a in alerts_ba if a.type == "interaction"]

        assert len(interaction_alerts_ab) > 0, "Expected interaction alert for ciprofloxacin + warfarin"
        assert len(interaction_alerts_ba) > 0, "Expected interaction alert for warfarin + ciprofloxacin"
        assert interaction_alerts_ab[0].message == interaction_alerts_ba[0].message

    @pytest.mark.asyncio
    async def test_no_false_positive_for_unrelated_drugs(self):
        """No interaction alert for drugs not in the interaction list."""
        service = AlertService()
        prescription = _make_prescription("amoxicillin")
        patient = _make_patient(["ibuprofen"])

        alerts = await service.check_prescription(prescription, patient)
        interaction_alerts = [a for a in alerts if a.type == "interaction"]

        assert len(interaction_alerts) == 0

    @pytest.mark.asyncio
    async def test_interaction_uses_cache_not_hardcoded(self):
        """_check_interactions uses _interactions_cache, not the module-level constant."""
        service = AlertService()
        # Override cache with a custom interaction
        service._interactions_cache = [
            ("custom_drug_a", "custom_drug_b", "Custom interaction message")
        ]

        prescription = _make_prescription("custom_drug_a")
        patient = _make_patient(["custom_drug_b"])

        alerts = await service.check_prescription(prescription, patient)
        interaction_alerts = [a for a in alerts if a.type == "interaction"]

        assert len(interaction_alerts) == 1
        assert interaction_alerts[0].message == "Custom interaction message"


# ---------------------------------------------------------------------------
# Property-based test — Property 15: Symmetry of drug interactions
# ---------------------------------------------------------------------------

# Feature: diagno-pilot-improvements, Property 15: Symétrie des interactions médicamenteuses
# Validates: Requirements 12.4

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    drug_b_idx=st.integers(min_value=0, max_value=len(_DRUG_INTERACTIONS) - 1),
)
def test_property_15_interaction_symmetry(drug_b_idx: int):
    """
    Property 15 — Symétrie des interactions médicamenteuses.

    For any pair (A, B) in drug_interactions, AlertService._check_interactions()
    must generate the same alert whether the pair is presented as
    (A prescribed, B in current medications) or (B prescribed, A in current medications).

    Validates: Requirements 12.4
    """
    import asyncio

    # Pick a known interaction pair
    interaction = _DRUG_INTERACTIONS[drug_b_idx]
    drug_a_name = interaction[0]
    drug_b_name = interaction[1]

    service = AlertService()

    prescription_ab = _make_prescription(drug_a_name)
    patient_ab = _make_patient([drug_b_name])

    prescription_ba = _make_prescription(drug_b_name)
    patient_ba = _make_patient([drug_a_name])

    alerts_ab = asyncio.run(service.check_prescription(prescription_ab, patient_ab))
    alerts_ba = asyncio.run(service.check_prescription(prescription_ba, patient_ba))

    interaction_msgs_ab = {a.message for a in alerts_ab if a.type == "interaction"}
    interaction_msgs_ba = {a.message for a in alerts_ba if a.type == "interaction"}

    assert interaction_msgs_ab == interaction_msgs_ba, (
        f"Asymmetric interaction for ({drug_a_name}, {drug_b_name}): "
        f"AB={interaction_msgs_ab}, BA={interaction_msgs_ba}"
    )
