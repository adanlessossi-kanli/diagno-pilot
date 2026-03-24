from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .alert import SafetyAlert


class Symptom(BaseModel):
    name: str
    severity: str | None = None
    duration_days: int | None = Field(default=None, ge=0)


class DifferentialDiagnosis(BaseModel):
    condition: str
    probability: float = Field(ge=0, le=1)
    icd_code: str | None = None
    matching_symptoms: list[str] = []


class Prescription(BaseModel):
    antibiotic: str
    dose_mg: float = Field(gt=0)
    dose_per_kg: float | None = None
    frequency: str
    duration_days: int = Field(gt=0)
    route: str  # oral | IV | IM
    is_capped_to_adult_dose: bool = False


class Consultation(BaseModel):
    id: str | None = None
    patient_id: str | None = None
    user_id: str
    symptoms: list[Symptom]
    diagnoses: list[DifferentialDiagnosis] = []
    prescription: Prescription | None = None
    alerts: list[SafetyAlert] = []
    llm_used: str | None = None
    is_one_shot: bool = False
    created_at: datetime | None = None


class ConsultationCreate(BaseModel):
    """Input model for creating a new consultation."""
    symptoms: list[Symptom]
    diagnoses: list[DifferentialDiagnosis] = []
    prescription: Prescription | None = None
    alerts: list[SafetyAlert] = []
    llm_used: str | None = None
