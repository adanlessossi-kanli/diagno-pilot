from fastapi import APIRouter, Depends, Query, status

from backend.core.auth import get_current_user
from backend.models.common import PaginatedResponse
from backend.models.consultation import Consultation, ConsultationCreate
from backend.models.patient import PatientCreate, PatientProfile
from backend.services import patient_service
from backend.services import consultation_service

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=PaginatedResponse[PatientProfile], status_code=status.HTTP_200_OK)
async def list_patients(
    page: int = Query(default=1, ge=1, description="Numéro de page (≥ 1)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Taille de page (1–100)"),
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/patients — liste paginée des patients de l'utilisateur authentifié."""
    items, total = await patient_service.list_patients(
        created_by=str(current_user["_id"]),
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse[PatientProfile](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


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
    """PUT /api/v1/patients/{id} — update an existing patient profile.

    age_group est recalculé automatiquement depuis date_of_birth via le
    model_validator de PatientCreate (REQ 13.4).
    """
    return await patient_service.update_patient(
        patient_id=patient_id, data=data, created_by=str(current_user["_id"])
    )


@router.get("/{patient_id}/consultations", response_model=list[Consultation], status_code=status.HTTP_200_OK)
async def list_consultations(
    patient_id: str,
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/patients/{id}/consultations — list all consultations for a patient."""
    return await consultation_service.list_consultations(
        patient_id=patient_id, user_id=str(current_user["_id"])
    )


@router.post("/{patient_id}/consultations", response_model=Consultation, status_code=status.HTTP_201_CREATED)
async def create_consultation(
    patient_id: str,
    data: ConsultationCreate,
    current_user: dict = Depends(get_current_user),
):
    """POST /api/v1/patients/{id}/consultations — create a new consultation for a patient."""
    return await consultation_service.create_consultation(
        patient_id=patient_id, data=data, user_id=str(current_user["_id"])
    )
