from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PatientFile(BaseModel):
    id: str | None = None
    patient_id: str
    consultation_id: str | None = None
    file_type: str  # lab_result | imaging | pdf | csv
    s3_key: str
    original_name: str
    size_bytes: int
    uploaded_by: str
    created_at: datetime | None = None
