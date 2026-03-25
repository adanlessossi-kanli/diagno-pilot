"""
Patient service — CRUD operations and age group computation.
Implements REQ-06 (patient profiles) and REQ-08 (paediatric age groups).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import HTTPException, status

from backend.core.database import db
from backend.models.common import AgeGroup
from backend.models.patient import PatientCreate, PatientProfile, Comorbidities


def _compute_age_group(dob: date) -> AgeGroup:
    today = date.today()
    delta_days = (today - dob).days
    if delta_days <= 28:
        return AgeGroup.NEONATAL
    delta_months = (today.year - dob.year) * 12 + (today.month - dob.month)
    if delta_months < 24:
        return AgeGroup.INFANT
    delta_years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if delta_years < 18:
        return AgeGroup.CHILD
    return AgeGroup.ADULT


def _doc_to_profile(doc: dict) -> PatientProfile:
    comorbidities = doc.get("comorbidities", {})
    dob_raw = doc.get("date_of_birth")
    dob: date | None = dob_raw.date() if isinstance(dob_raw, datetime) else dob_raw
    return PatientProfile(
        id=str(doc["_id"]),
        full_name=doc.get("full_name", ""),
        date_of_birth=dob,
        weight_kg=doc.get("weight_kg"),
        age_group=doc.get("age_group"),
        allergies=doc.get("allergies", []),
        comorbidities=Comorbidities(
            renal_failure=comorbidities.get("renal_failure", False),
            hepatic_failure=comorbidities.get("hepatic_failure", False),
        ),
        current_medications=doc.get("current_medications", []),
        created_by=str(doc["created_by"]) if doc.get("created_by") else None,
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


async def list_patients(
    created_by: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PatientProfile], int]:
    """Retourne les patients paginés créés par l'utilisateur donné.

    Retourne un tuple (items, total) où items est la page demandée et total
    est le nombre total de patients.
    """
    database = db.get_db()
    query = {"created_by": ObjectId(created_by)}
    total = await database["patients"].count_documents(query)

    skip = (page - 1) * page_size
    # Si la page demandée dépasse le total, retourner une liste vide (REQ 8.3)
    if total == 0 or skip >= total:
        return [], total

    cursor = database["patients"].find(query).skip(skip).limit(page_size)
    docs = await cursor.to_list(length=page_size)
    return [_doc_to_profile(d) for d in docs], total


async def create_patient(data: PatientCreate, created_by: str) -> PatientProfile:
    """Insert a new patient document and return the created profile."""
    now = datetime.now(timezone.utc)
    age_group: Optional[AgeGroup] = None
    if data.date_of_birth:
        age_group = _compute_age_group(data.date_of_birth)

    doc = {
        "full_name": data.full_name,
        "date_of_birth": datetime.combine(data.date_of_birth, datetime.min.time()) if data.date_of_birth else None,
        "weight_kg": data.weight_kg,
        "age_group": age_group.value if age_group else None,
        "allergies": data.allergies,
        "comorbidities": {
            "renal_failure": data.comorbidities.renal_failure,
            "hepatic_failure": data.comorbidities.hepatic_failure,
        },
        "current_medications": data.current_medications,
        "created_by": ObjectId(created_by),
        "created_at": now,
        "updated_at": now,
    }

    database = db.get_db()
    result = await database["patients"].insert_one(doc)
    doc["_id"] = result.inserted_id
    doc["age_group"] = age_group
    return _doc_to_profile(doc)


async def get_patient(patient_id: str, created_by: str) -> PatientProfile:
    """Fetch a single patient by id, scoped to the requesting user."""
    try:
        oid = ObjectId(patient_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    database = db.get_db()
    doc = await database["patients"].find_one({"_id": oid, "created_by": ObjectId(created_by)})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return _doc_to_profile(doc)


async def update_patient(patient_id: str, data: PatientCreate, created_by: str) -> PatientProfile:
    """Update an existing patient document."""
    try:
        oid = ObjectId(patient_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    now = datetime.now(timezone.utc)
    age_group: Optional[AgeGroup] = None
    if data.date_of_birth:
        age_group = _compute_age_group(data.date_of_birth)

    update_fields = {
        "full_name": data.full_name,
        "date_of_birth": datetime.combine(data.date_of_birth, datetime.min.time()) if data.date_of_birth else None,
        "weight_kg": data.weight_kg,
        "age_group": age_group.value if age_group else None,
        "allergies": data.allergies,
        "comorbidities": {
            "renal_failure": data.comorbidities.renal_failure,
            "hepatic_failure": data.comorbidities.hepatic_failure,
        },
        "current_medications": data.current_medications,
        "updated_at": now,
    }

    database = db.get_db()
    result = await database["patients"].find_one_and_update(
        {"_id": oid, "created_by": ObjectId(created_by)},
        {"$set": update_fields},
        return_document=True,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    result["age_group"] = age_group
    return _doc_to_profile(result)
