from fastapi import APIRouter, Depends, status

from backend.core.auth import get_current_user
from backend.models.patient import PatientCreate, PatientProfile
from backend.services import patient_service

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=list[PatientProfile], status_code=status.HTTP_200_OK)
async def list_patients(current_user: dict = Depends(get_current_user)):
    """GET /api/v1/patients — list all patients belonging to the authenticated user."""
    return await patient_service.list_patients(created_by=str(current_user["_id"]))


@router.post("", response_model=PatientProfile, status_code=status.HTTP_201_CREATED)
async def create_patient(
    data: PatientCreate,
    current_user: dict = Depends(get_current_user),
):
    """POST /api/v1/patients — create a new patient profile."""
    return await patient_service.create_patient(data=data, created_by=str(current_user["_id"]))


@router.get("/{patient_id}", response_model=PatientProfile, status_code=status.HTTP_200_OK)
async def get_patient(
    patient_id: str,
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/patients/{id} — retrieve a patient by id."""
    return await patient_service.get_patient(
        patient_id=patient_id, created_by=str(current_user["_id"])
    )


@router.put("/{patient_id}", response_model=PatientProfile, status_code=status.HTTP_200_OK)
async def update_patient(
    patient_id: str,
    data: PatientCreate,
    current_user: dict = Depends(get_current_user),
):
    """PUT /api/v1/patients/{id} — update an existing patient profile."""
    return await patient_service.update_patient(
        patient_id=patient_id, data=data, created_by=str(current_user["_id"])
    )
