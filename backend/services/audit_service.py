"""
Service d'audit et de traçabilité — Diagno-Pilot

Persiste les logs d'audit dans la collection ``audit_logs`` MongoDB
(service historique) et dans ``hipaa_audit_logs`` (AuditLogger HIPAA).

Validates: REQ-10, Requirements 8.1, 8.2, 8.3, 8.5, 8.6
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.core.database import db
from backend.core.db_metrics import timed_db_op

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Existing AuditService — backward compatible
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# HIPAA-compliant AuditLogger with hash chain (Requirements 8.x)
# ---------------------------------------------------------------------------

_DEFAULT_FALLBACK_PATH = "/var/log/diagno-pilot/audit_fallback.jsonl"


class AuditLogger:
    """Journal d'audit HIPAA avec chaîne de hachage anti-falsification.

    * Collection ``hipaa_audit_logs`` — append-only (no update/delete).
    * Chaque enregistrement contient ``SHA-256(previous_hash + json(record))``.
    * Fallback vers un fichier JSONL local si l'écriture MongoDB échoue.

    Validates: Requirements 8.1, 8.2, 8.3, 8.5, 8.6
    """

    COLLECTION = "hipaa_audit_logs"

    def __init__(
        self,
        database: Any | None = None,
        fallback_path: str = _DEFAULT_FALLBACK_PATH,
    ) -> None:
        self._database = database
        self._fallback_path = fallback_path
        self._last_hash: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def log_action(
        self,
        user_id: str,
        action: str,
        resource: str,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> str:
        """Persist a HIPAA audit record with hash-chain integrity.

        Returns the record id (UUID).
        """
        record_id = str(uuid4())
        timestamp = datetime.now(timezone.utc)

        record_data = {
            "id": record_id,
            "timestamp": timestamp.isoformat(),
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
            "details": dict(details) if details else {},
            "ip_address": ip_address,
        }

        previous_hash = self._last_hash
        record_hash = self._compute_hash(previous_hash, record_data)

        document = {
            **record_data,
            "previous_hash": previous_hash,
            "record_hash": record_hash,
        }

        try:
            database = self._database or db.get_db()
            async with timed_db_op(self.COLLECTION, "insert_one"):
                await database[self.COLLECTION].insert_one(document)
            self._last_hash = record_hash
        except Exception:
            logger.error("HIPAA audit write to MongoDB failed — using fallback file")
            try:
                await self._write_fallback(document)
                self._last_hash = record_hash
            except Exception:
                logger.critical(
                    "HIPAA audit fallback write also failed for record %s",
                    record_id,
                )
                raise

        return record_id

    async def verify_chain(
        self,
        records: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Verify hash-chain integrity.

        If *records* is ``None``, reads all records from MongoDB sorted by
        timestamp.  Returns ``True`` when the chain is intact.
        """
        if records is None:
            database = self._database or db.get_db()
            cursor = database[self.COLLECTION].find().sort("timestamp", 1)
            records = await cursor.to_list(length=None)

        previous_hash = ""
        for rec in records:
            record_data = {
                "id": rec["id"],
                "timestamp": rec["timestamp"],
                "user_id": rec["user_id"],
                "action": rec["action"],
                "resource": rec["resource"],
                "resource_id": rec.get("resource_id"),
                "details": rec.get("details", {}),
                "ip_address": rec.get("ip_address"),
            }
            expected = self._compute_hash(previous_hash, record_data)
            if rec.get("record_hash") != expected:
                return False
            if rec.get("previous_hash") != previous_hash:
                return False
            previous_hash = rec["record_hash"]
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_hash(previous_hash: str, record_data: dict[str, Any]) -> str:
        """``SHA-256(previous_hash + json(record_data))``."""
        payload = previous_hash + json.dumps(record_data, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def _write_fallback(self, record: dict[str, Any]) -> None:
        """Append *record* as a JSON line to the local fallback file."""
        path = Path(self._fallback_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, default=str) + "\n"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)


# Module-level singletons
audit_service = AuditService()
audit_logger = AuditLogger()
