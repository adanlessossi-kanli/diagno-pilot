"""
Consultation service — persist and retrieve consultations.
Implements REQ-07 (patient dossier and consultation history).
"""
from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from backend.core.database import db
from backend.core.db_metrics import timed_db_op
from backend.models.consultation import Consultation, ConsultationCreate


def _doc_to_consultation(doc: dict) -> Consultation:
    return Consultation(
        id=str(doc["_id"]),
        patient_id=str(doc["patient_id"]) if doc.get("patient_id") else None,
        user_id=str(doc["user_id"]),
        symptoms=doc.get("symptoms", []),
        diagnoses=doc.get("diagnoses", []),
        prescription=doc.get("prescription"),
        alerts=doc.get("alerts", []),
        llm_used=doc.get("llm_used"),
        is_one_shot=doc.get("is_one_shot", False),
        created_at=doc.get("created_at"),
    )


async def list_consultations(patient_id: str, user_id: str) -> list[Consultation]:
    """Return all consultations for a patient, scoped to the requesting user."""
    try:
        patient_oid = ObjectId(patient_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    database = db.get_db()
    async with timed_db_op("consultations", "find"):
        cursor = database["consultations"].find(
            {"patient_id": patient_oid, "user_id": ObjectId(user_id)}
        )
        docs = await cursor.to_list(length=None)
    return [_doc_to_consultation(d) for d in docs]


async def create_consultation(
    patient_id: str | None,
    data: ConsultationCreate,
    user_id: str,
) -> Consultation:
    """Insert a new consultation document and return it."""
    now = datetime.now(timezone.utc)
    is_one_shot = patient_id is None

    doc: dict = {
        "patient_id": ObjectId(patient_id) if patient_id else None,
        "user_id": ObjectId(user_id),
        "symptoms": [s.model_dump() for s in data.symptoms],
        "diagnoses": [d.model_dump() for d in data.diagnoses],
        "prescription": data.prescription.model_dump() if data.prescription else None,
        "alerts": [a.model_dump() for a in data.alerts],
        "llm_used": data.llm_used,
        "is_one_shot": is_one_shot,
        "created_at": now,
    }

    database = db.get_db()
    async with timed_db_op("consultations", "insert_one"):
        result = await database["consultations"].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_consultation(doc)
