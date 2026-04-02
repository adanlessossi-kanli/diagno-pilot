"""Alerts router — safety alert endpoints (REQ-09)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from backend.core.auth import get_current_user
from backend.models.alert import SafetyAlert
from backend.models.consultation import Prescription
from backend.models.patient import PatientProfile
from backend.services.alert_service import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class AlertCheckRequest(BaseModel):
    prescription: Prescription
    patient_profile: PatientProfile


class AlertCheckResponse(BaseModel):
    alerts: list[SafetyAlert]


# ---------------------------------------------------------------------------
# GET /api/v1/alerts/check
# ---------------------------------------------------------------------------

@router.get(
    "/check",
    response_model=AlertCheckResponse,
    status_code=status.HTTP_200_OK,
)
async def check_alerts(
    antibiotic: str,
    patient_id: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/alerts/check

    Quick alert check for a given antibiotic and optional patient.
    Returns any safety alerts (allergies, interactions, contraindications)
    without persisting a prescription.

    Query parameters:
    - antibiotic: name of the antibiotic to check
    - patient_id: (optional) patient id to load allergies / comorbidities from DB
    """
    from backend.core.database import db
    from backend.core.db_metrics import timed_db_op
    from backend.models.patient import Comorbidities
    from bson import ObjectId

    # Build a minimal patient profile
    if patient_id:
        try:
            oid = ObjectId(patient_id)
        except Exception:
            oid = None

        patient: PatientProfile | None = None
        if oid:
            database = db.get_db()
            async with timed_db_op("patients", "find_one"):
                doc = await database["patients"].find_one({"_id": oid})
            if doc:
                comorbidities_raw = doc.get("comorbidities", {})
                patient = PatientProfile(
                    id=str(doc["_id"]),
                    full_name=doc.get("full_name", ""),
                    allergies=doc.get("allergies", []),
                    comorbidities=Comorbidities(
                        renal_failure=comorbidities_raw.get("renal_failure", False),
                        hepatic_failure=comorbidities_raw.get("hepatic_failure", False),
                    ),
                    age_group=doc.get("age_group"),
                    current_medications=doc.get("current_medications", []),
                )

        if patient is None:
            patient = PatientProfile(full_name="unknown")
    else:
        patient = PatientProfile(full_name="unknown")

    # Build a minimal prescription for the check
    from backend.services.prescription_service import ANTIBIOTIC_PROTOCOLS
    protocol = ANTIBIOTIC_PROTOCOLS.get(antibiotic.lower())
    rx = Prescription(
        antibiotic=antibiotic,
        dose_mg=protocol.adult_max_dose_mg if protocol else 0.0,
        frequency=protocol.frequency if protocol else "unknown",
        duration_days=protocol.duration_days if protocol else 1,
        route=protocol.route if protocol else "oral",
    )

    alerts = await alert_service.check_prescription(prescription=rx, patient=patient)
    return AlertCheckResponse(alerts=alerts)
