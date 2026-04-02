"""
Service d'audit et de traçabilité — Diagno-Pilot

Persiste les logs d'audit dans la collection `audit_logs` MongoDB.
Validates: REQ-10
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.core.database import db
from backend.core.db_metrics import timed_db_op


class AuditService:
    """Enregistre les actions sensibles dans la collection `audit_logs`."""

    async def log_action(
        self,
        user_id: str,
        action: str,
        resource: str,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        locale: str | None = None,
        region: str | None = None,
    ) -> str:
        """Persiste un log d'audit et retourne l'id du document créé."""
        merged_details: dict[str, Any] = dict(details) if details else {}
        if locale is not None:
            merged_details["locale"] = locale
        if region is not None:
            merged_details["region"] = region
        document = {
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
            "details": merged_details,
            "ip_address": ip_address,
            "created_at": datetime.now(timezone.utc),
        }
        database = db.get_db()
        async with timed_db_op("audit_logs", "insert_one"):
            result = await database["audit_logs"].insert_one(document)
        return str(result.inserted_id)


# Module-level singleton
audit_service = AuditService()
