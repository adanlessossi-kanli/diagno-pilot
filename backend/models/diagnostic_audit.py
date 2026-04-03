"""DiagnosticAudit models — REQ 4.3, 4.4, 4.8."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import BaseModel


class AgentAuditResult(BaseModel):
    agent_name: str
    sub_question: str
    chunk_ids: list[str]
    confidence_score: float
    partial_differential: list[dict]


class DiagnosticAudit(BaseModel):
    timestamp: datetime
    symptoms: list[dict]
    patient_profile_hash: str  # SHA-256 over age, weight, sex, comorbidities only
    locale: str
    region: str | None
    confidence_score: float
    diagnoses: list[dict]
    fallback_used: bool
    degraded_warning: str | None
    agent_results: list[AgentAuditResult]

    @staticmethod
    def compute_patient_hash(
        age: int | None,
        weight: float | None,
        sex: str | None,
        comorbidities: dict | None,
    ) -> str:
        """Compute SHA-256 hash over non-PII patient fields only."""
        payload = json.dumps(
            {"age": age, "weight": weight, "sex": sex, "comorbidities": comorbidities},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()
