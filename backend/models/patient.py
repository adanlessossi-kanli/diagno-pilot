from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from .common import AgeGroup


def _compute_age_group(dob: date) -> AgeGroup:
    """Calcule le groupe d'âge depuis la date de naissance.

    Règles :
    - 0–28 jours      → neonatal
    - 29 jours–23 mois → infant
    - 2–17 ans         → child
    - 18 ans et plus   → adult
    """
    today = date.today()
    delta_days = (today - dob).days

    if delta_days <= 28:
        return AgeGroup.NEONATAL

    # 29 jours–23 mois : moins de 2 ans complets
    # Handle leap day birthdays (Feb 29) in non-leap years → use Feb 28
    try:
        two_years_later = date(dob.year + 2, dob.month, dob.day)
    except ValueError:
        two_years_later = date(dob.year + 2, dob.month, 28)
    if today < two_years_later:
        return AgeGroup.INFANT

    # 2–17 ans : moins de 18 ans complets
    try:
        eighteen_years_later = date(dob.year + 18, dob.month, dob.day)
    except ValueError:
        eighteen_years_later = date(dob.year + 18, dob.month, 28)
    if today < eighteen_years_later:
        return AgeGroup.CHILD

    return AgeGroup.ADULT


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
