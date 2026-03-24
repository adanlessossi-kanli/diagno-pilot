"""Diagnose router — differential diagnosis endpoints (REQ-02)."""
from __future__ import annotations

import uuid
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.core.auth import get_current_user
from backend.core.database import db
from backend.models.consultation import Consultation, DifferentialDiagnosis, Symptom
from backend.models.patient import PatientProfile
from backend.services.diagnostic_service import DiagnosticService
from backend.services.embedding_service import EmbeddingModel
from backend.services.llm_router import LLMRouter
from backend.services.rag_service import RAGService
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

def get_diagnostic_service() -> DiagnosticService:
    """Build DiagnosticService from the shared DB connection."""
    database = db.get_db()
    # Access the underlying Motor client via the database proxy
    mongo_client = database.client
    llm_router = LLMRouter()
    embedder = EmbeddingModel()
    rag = RAGService(
        mongo_client=mongo_client,
        llm_router=llm_router,
        embedder=embedder,
        db_name=database.name,
    )
    return DiagnosticService(rag_service=rag)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/symptoms",
    response_model=DiagnoseResponse,
    status_code=status.HTTP_200_OK,
)
async def diagnose_symptoms(
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
    now = datetime.utcnow()

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
