"""
Tests unitaires pour le service patient — Diagno-Pilot
Validates: Requirements REQ-06
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException

from backend.models.common import AgeGroup
from backend.models.patient import PatientCreate
from backend.services.patient_service import _compute_age_group, create_patient, get_patient, update_patient


# ---------------------------------------------------------------------------
# 1. _compute_age_group — boundary tests (no DB)
# ---------------------------------------------------------------------------

class TestComputeAgeGroup:
    def test_today_is_neonatal(self):
        assert _compute_age_group(date.today()) == AgeGroup.NEONATAL

    def test_28_days_is_neonatal(self):
        dob = date.today() - timedelta(days=28)
        assert _compute_age_group(dob) == AgeGroup.NEONATAL

    def test_29_days_is_infant(self):
        dob = date.today() - timedelta(days=29)
        assert _compute_age_group(dob) == AgeGroup.INFANT

    def test_23_months_is_infant(self):
        # Simpler: use timedelta approximation (23 * 30 days)
        dob = date.today() - timedelta(days=23 * 30)
        assert _compute_age_group(dob) == AgeGroup.INFANT

    def test_24_months_is_child(self):
        # 24 months = 2 years exactly
        today = date.today()
        try:
            dob = today.replace(year=today.year - 2)
        except ValueError:
            dob = today.replace(year=today.year - 2, day=28)
        assert _compute_age_group(dob) == AgeGroup.CHILD

    def test_17_years_is_child(self):
        today = date.today()
        try:
            dob = today.replace(year=today.year - 17)
        except ValueError:
            dob = today.replace(year=today.year - 17, day=28)
        assert _compute_age_group(dob) == AgeGroup.CHILD

    def test_18_years_is_adult(self):
        today = date.today()
        try:
            dob = today.replace(year=today.year - 18)
        except ValueError:
            dob = today.replace(year=today.year - 18, day=28)
        assert _compute_age_group(dob) == AgeGroup.ADULT

    def test_50_years_is_adult(self):
        today = date.today()
        try:
            dob = today.replace(year=today.year - 50)
        except ValueError:
            dob = today.replace(year=today.year - 50, day=28)
        assert _compute_age_group(dob) == AgeGroup.ADULT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db(collection_mock: MagicMock) -> MagicMock:
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=collection_mock)
    return mock_db


def _make_patient_doc(patient_id: ObjectId, dob: date | None = None, age_group: str | None = None) -> dict:
    return {
        "_id": patient_id,
        "full_name": "Alice Dupont",
        "date_of_birth": datetime.combine(dob, datetime.min.time()) if dob else None,
        "weight_kg": 65.0,
        "age_group": age_group,
        "allergies": ["pénicilline"],
        "comorbidities": {"renal_failure": False, "hepatic_failure": False},
        "current_medications": [],
        "created_by": ObjectId(),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


# ---------------------------------------------------------------------------
# 2. create_patient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCreatePatient:
    async def test_inserts_document_and_returns_profile_with_age_group(self):
        today = date.today()
        try:
            dob = today.replace(year=today.year - 30)
        except ValueError:
            dob = today.replace(year=today.year - 30, day=28)

        data = PatientCreate(full_name="Alice Dupont", date_of_birth=dob, weight_kg=65.0)
        created_by = str(ObjectId())
        inserted_id = ObjectId()

        collection_mock = MagicMock()
        insert_result = MagicMock()
        insert_result.inserted_id = inserted_id
        collection_mock.insert_one = AsyncMock(return_value=insert_result)

        mock_db = _make_mock_db(collection_mock)

        with patch("backend.services.patient_service.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db
            profile = await create_patient(data, created_by)

        collection_mock.insert_one.assert_called_once()
        assert profile.full_name == "Alice Dupont"
        assert profile.age_group == AgeGroup.ADULT
        assert str(profile.id) == str(inserted_id)

    async def test_create_patient_without_dob_has_no_age_group(self):
        data = PatientCreate(full_name="Bob Martin")
        created_by = str(ObjectId())
        inserted_id = ObjectId()

        collection_mock = MagicMock()
        insert_result = MagicMock()
        insert_result.inserted_id = inserted_id
        collection_mock.insert_one = AsyncMock(return_value=insert_result)

        mock_db = _make_mock_db(collection_mock)

        with patch("backend.services.patient_service.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db
            profile = await create_patient(data, created_by)

        assert profile.age_group is None


# ---------------------------------------------------------------------------
# 3. get_patient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetPatient:
    async def test_returns_correct_patient_when_found(self):
        patient_id = ObjectId()
        created_by = str(ObjectId())
        dob = date(1990, 5, 15)
        doc = _make_patient_doc(patient_id, dob=dob, age_group="adult")

        collection_mock = MagicMock()
        collection_mock.find_one = AsyncMock(return_value=doc)
        mock_db = _make_mock_db(collection_mock)

        with patch("backend.services.patient_service.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db
            profile = await get_patient(str(patient_id), created_by)

        assert profile.full_name == "Alice Dupont"
        assert str(profile.id) == str(patient_id)

    async def test_raises_404_when_not_found(self):
        patient_id = ObjectId()
        created_by = str(ObjectId())

        collection_mock = MagicMock()
        collection_mock.find_one = AsyncMock(return_value=None)
        mock_db = _make_mock_db(collection_mock)

        with patch("backend.services.patient_service.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db
            with pytest.raises(HTTPException) as exc_info:
                await get_patient(str(patient_id), created_by)

        assert exc_info.value.status_code == 404

    async def test_raises_404_for_invalid_object_id(self):
        with pytest.raises(HTTPException) as exc_info:
            await get_patient("not-a-valid-id", str(ObjectId()))
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 4. update_patient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestUpdatePatient:
    async def test_updates_fields_and_recalculates_age_group(self):
        patient_id = ObjectId()
        created_by = str(ObjectId())
        today = date.today()
        try:
            new_dob = today.replace(year=today.year - 5)
        except ValueError:
            new_dob = today.replace(year=today.year - 5, day=28)

        data = PatientCreate(full_name="Alice Updated", date_of_birth=new_dob, weight_kg=20.0)

        updated_doc = _make_patient_doc(patient_id, dob=new_dob, age_group="child")
        updated_doc["full_name"] = "Alice Updated"
        updated_doc["weight_kg"] = 20.0

        collection_mock = MagicMock()
        collection_mock.find_one_and_update = AsyncMock(return_value=updated_doc)
        mock_db = _make_mock_db(collection_mock)

        with patch("backend.services.patient_service.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db
            profile = await update_patient(str(patient_id), data, created_by)

        collection_mock.find_one_and_update.assert_called_once()
        assert profile.full_name == "Alice Updated"
        assert profile.age_group == AgeGroup.CHILD

    async def test_raises_404_when_patient_not_found(self):
        patient_id = ObjectId()
        created_by = str(ObjectId())
        data = PatientCreate(full_name="Ghost Patient")

        collection_mock = MagicMock()
        collection_mock.find_one_and_update = AsyncMock(return_value=None)
        mock_db = _make_mock_db(collection_mock)

        with patch("backend.services.patient_service.db") as mock_db_obj:
            mock_db_obj.get_db.return_value = mock_db
            with pytest.raises(HTTPException) as exc_info:
                await update_patient(str(patient_id), data, created_by)

        assert exc_info.value.status_code == 404

    async def test_raises_404_for_invalid_object_id(self):
        data = PatientCreate(full_name="X")
        with pytest.raises(HTTPException) as exc_info:
            await update_patient("bad-id", data, str(ObjectId()))
        assert exc_info.value.status_code == 404
