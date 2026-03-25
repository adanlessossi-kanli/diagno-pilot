"""Diagnose router — differential diagnosis and prescription endpoints (REQ-02, REQ-03, REQ-09)."""

import uuid
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.core.auth import get_current_user
from backend.core.database import db
from backend.core.rate_limit import limiter
from backend.models.alert import SafetyAlert
from backend.models.consultation import Consultation, DifferentialDiagnosis, Prescription, Symptom
from backend.models.patient import PatientProfile
from backend.services.alert_service import alert_service
from backend.services.diagnostic_service import DiagnosticService
from backend.services.prescription_service import prescription_service
from pydantic import BaseModel

router = APIRouter(prefix="/diagnose", tags=["diagnose"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class DiagnoseRequest(BaseModel):
    symptoms: list[Symptom]
    patient_profile: PatientProfile | None = None
    session_id: str | None = None


class DiagnoseResponse(BaseModel):
    session_id: str
    diagnoses: list[DifferentialDiagnosis]


# ---------------------------------------------------------------------------
# Dependency: DiagnosticService
# ---------------------------------------------------------------------------

def get_diagnostic_service(request: Request) -> DiagnosticService:
    """Return the DiagnosticService singleton stored in app.state (REQ 6.5)."""
    return request.app.state.diagnostic_service


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/symptoms",
    response_model=DiagnoseResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("30/minute")
async def diagnose_symptoms(
    request: Request,
    body: DiagnoseRequest,
    current_user: dict = Depends(get_current_user),
    diagnostic_service: DiagnosticService = Depends(get_diagnostic_service),
):
    """POST /api/v1/diagnose/symptoms

    Accepts a list of symptoms and an optional patient profile, calls the
    DiagnosticService to generate differential diagnoses, persists the session
    in MongoDB, and returns the session_id together with the diagnoses.
    """
    diagnoses = await diagnostic_service.get_differential_diagnosis(
        symptoms=body.symptoms,
        patient_profile=body.patient_profile,
    )

    session_id = body.session_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    doc: dict = {
        "_id": ObjectId(),
        "session_id": session_id,
        "patient_id": None,
        "user_id": ObjectId(str(current_user["_id"])),
        "symptoms": [s.model_dump() for s in body.symptoms],
        "diagnoses": [d.model_dump() for d in diagnoses],
        "prescription": None,
        "alerts": [],
        "llm_used": None,
        "is_one_shot": True,
        "created_at": now,
    }

    database = db.get_db()
    await database["consultations"].insert_one(doc)

    return DiagnoseResponse(session_id=session_id, diagnoses=diagnoses)


@router.get(
    "/session/{session_id}",
    response_model=Consultation,
    status_code=status.HTTP_200_OK,
)
async def get_diagnosis_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/diagnose/session/{session_id}

    Retrieves a stored diagnosis session from MongoDB by session_id.
    """
    database = db.get_db()
    doc = await database["consultations"].find_one({"session_id": session_id})

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return Consultation(
        id=str(doc["_id"]),
        patient_id=str(doc["patient_id"]) if doc.get("patient_id") else None,
        user_id=str(doc["user_id"]),
        symptoms=doc.get("symptoms", []),
        diagnoses=doc.get("diagnoses", []),
        prescription=doc.get("prescription"),
        alerts=doc.get("alerts", []),
        llm_used=doc.get("llm_used"),
        is_one_shot=doc.get("is_one_shot", True),
        created_at=doc.get("created_at"),
    )


# ---------------------------------------------------------------------------
# Prescription endpoint models
# ---------------------------------------------------------------------------

class PrescriptionRequest(BaseModel):
    antibiotic: str
    patient_profile: PatientProfile


class PrescriptionResponse(BaseModel):
    prescription: Prescription
    alerts: list[SafetyAlert]


# ---------------------------------------------------------------------------
# POST /api/v1/diagnose/prescription
# ---------------------------------------------------------------------------

@router.post(
    "/prescription",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_200_OK,
)
async def create_prescription(
    body: PrescriptionRequest,
    current_user: dict = Depends(get_current_user),
):
    """POST /api/v1/diagnose/prescription

    Calculates an antibiotic prescription adapted to the patient profile
    (weight-based dosing, renal/hepatic adjustments) and runs safety checks
    (allergies, interactions, age contraindications).

    Returns the prescription together with any safety alerts.
    """
    try:
        rx = prescription_service.calculate_prescription(
            antibiotic=body.antibiotic,
            patient=body.patient_profile,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    alerts = await alert_service.check_prescription(
        prescription=rx,
        patient=body.patient_profile,
    )

    return PrescriptionResponse(prescription=rx, alerts=alerts)
