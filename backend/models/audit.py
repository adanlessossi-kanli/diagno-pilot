from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditLog(BaseModel):
    id: str | None = None
    user_id: str
    action: str
    resource: str
    resource_id: str | None = None
    details: dict = {}
    ip_address: str | None = None
    created_at: datetime | None = None
