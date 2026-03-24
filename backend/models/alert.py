from __future__ import annotations

from pydantic import BaseModel

from .common import AlertLevel


class SafetyAlert(BaseModel):
    level: AlertLevel
    type: str  # allergy | interaction | contraindication
    message: str
    affected_drug: str | None = None
    alternative: str | None = None
