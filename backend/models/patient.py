from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from .common import AgeGroup


class Comorbidities(BaseModel):
    renal_failure: bool = False
    hepatic_failure: bool = False


class PatientProfile(BaseModel):
    id: str | None = None
    full_name: str
    date_of_birth: date | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    age_group: AgeGroup | None = None
    allergies: list[str] = []
    comorbidities: Comorbidities = Field(default_factory=Comorbidities)
    current_medications: list[str] = []
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PatientCreate(BaseModel):
    full_name: str
    date_of_birth: date | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    allergies: list[str] = []
    comorbidities: Comorbidities = Field(default_factory=Comorbidities)
    current_medications: list[str] = []
