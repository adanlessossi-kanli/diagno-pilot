from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from .common import AgeGroup
from backend.utils.age import compute_age_group as _compute_age_group


class Comorbidities(BaseModel):
    renal_failure: bool = False
    hepatic_failure: bool = False


class PatientProfile(BaseModel):
    id: str | None = None
    full_name: str | None = None
    date_of_birth: date | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    age_group: AgeGroup | None = None
    allergies: list[str] = []
    comorbidities: Comorbidities = Field(default_factory=Comorbidities)
    current_medications: list[str] = []
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def compute_age_group(self) -> "PatientProfile":
        if self.date_of_birth is not None:
            self.age_group = _compute_age_group(self.date_of_birth)
        return self


class PatientCreate(BaseModel):
    full_name: str
    date_of_birth: date | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    age_group: AgeGroup | None = None
    allergies: list[str] = []
    comorbidities: Comorbidities = Field(default_factory=Comorbidities)
    current_medications: list[str] = []

    @model_validator(mode="after")
    def compute_age_group(self) -> "PatientCreate":
        if self.date_of_birth is not None:
            self.age_group = _compute_age_group(self.date_of_birth)
        return self
