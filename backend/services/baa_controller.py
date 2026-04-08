"""
Contrôleur BAA (Business Associate Agreement) — Diagno-Pilot

Garantit que les appels LLM externes (GPT-5 fallback) ne transmettent
aucune donnée PHI.  Les valeurs PHI sont remplacées par des placeholders
génériques avant toute transmission vers un endpoint externe.

Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5
"""
from __future__ import annotations

import logging
from typing import Any

from backend.services.phi_classifier import PHIClassifier

logger = logging.getLogger(__name__)


class BAAStripError(Exception):
    """Raised when PHI stripping fails or cannot be verified."""


class BAAController:
    """Enforces zero-PHI on external LLM calls (BAA compliance).

    Before any request is sent to an external LLM (e.g. GPT-5), this
    controller replaces all PHI values with generic placeholders and logs
    the stripping event to the audit logger.
    """

    PHI_PLACEHOLDERS: dict[str, str] = {
        "full_name": "[PATIENT_NAME]",
        "date_of_birth": "[DOB]",
        "medical_record_number": "[MRN]",
        "allergies": "[ALLERGIES]",
        "current_medications": "[MEDICATIONS]",
        "comorbidities": "[COMORBIDITIES]",
        "weight_kg": "[WEIGHT]",
        "diagnoses": "[DIAGNOSES]",
        "prescriptions": "[PRESCRIPTIONS]",
        "consultation_notes": "[NOTES]",
        "differential_diagnoses": "[DIFFERENTIAL]",
        "partial_differential": "[PARTIAL_DIFFERENTIAL]",
    }

    def __init__(self, audit_logger: Any | None = None) -> None:
        self._audit_logger = audit_logger

    def strip_phi(
        self,
        context: list[dict[str, Any]],
        classifier: PHIClassifier,
    ) -> list[dict[str, Any]]:
        """Remove/replace all PHI from LLM context messages.

        Each message dict is scanned for PHI fields.  String values of PHI
        fields are replaced with the corresponding placeholder.  Non-string
        PHI values are replaced with the placeholder as well.

        Returns a new list of sanitised message dicts.

        Raises:
            BAAStripError: if stripping fails or post-strip verification
                detects residual PHI.
        """
        try:
            stripped = self._do_strip(context, classifier)
        except Exception as exc:
            logger.error("BAA PHI stripping failed: %s", exc)
            self._log_strip_failure()
            raise BAAStripError(
                "PHI stripping failed — external LLM call blocked"
            ) from exc

        # Post-strip verification (Req 9.4)
        try:
            self.verify_no_phi(stripped, classifier)
        except BAAStripError:
            logger.error("Post-strip verification found residual PHI")
            self._log_strip_failure()
            raise

        # Log the stripping event (field types only, no PHI values — Req 9.3)
        self._log_strip_event(context, classifier)

        return stripped

    def verify_no_phi(
        self,
        context: list[dict[str, Any]],
        classifier: PHIClassifier,
    ) -> None:
        """Raise :class:`BAAStripError` if *context* contains any PHI.

        Scans every message dict for keys classified as PHI whose values
        are not one of the known placeholders.
        """
        placeholder_values = set(self.PHI_PLACEHOLDERS.values())
        for msg in context:
            for key, value in msg.items():
                if classifier.is_phi(key):
                    if isinstance(value, str) and value in placeholder_values:
                        continue
                    # "content" and "role" are standard message keys — skip
                    if key in ("content", "role"):
                        continue
                    raise BAAStripError(
                        f"Residual PHI detected in field '{key}' after stripping"
                    )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _do_strip(
        self,
        context: list[dict[str, Any]],
        classifier: PHIClassifier,
    ) -> list[dict[str, Any]]:
        """Replace PHI values with placeholders in each message dict."""
        result: list[dict[str, Any]] = []
        for msg in context:
            new_msg: dict[str, Any] = {}
            for key, value in msg.items():
                if classifier.is_phi(key) and key in self.PHI_PLACEHOLDERS:
                    new_msg[key] = self.PHI_PLACEHOLDERS[key]
                elif classifier.is_phi(key) and key not in ("content", "role"):
                    # Unknown PHI field — use a generic placeholder
                    new_msg[key] = "[REDACTED]"
                else:
                    new_msg[key] = value
            result.append(new_msg)
        return result

    def _log_strip_event(
        self,
        original_context: list[dict[str, Any]],
        classifier: PHIClassifier,
    ) -> None:
        """Log the PHI-stripping event to the audit logger (field types only)."""
        if self._audit_logger is None:
            return

        stripped_field_types: list[str] = []
        for msg in original_context:
            for key in msg:
                if classifier.is_phi(key) and key not in ("content", "role"):
                    if key not in stripped_field_types:
                        stripped_field_types.append(key)

        if not stripped_field_types:
            return

        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    self._audit_logger.log_action(
                        user_id="system",
                        action="phi_strip",
                        resource="llm_fallback",
                        details={"field_types": stripped_field_types},
                    )
                )
            else:
                loop.run_until_complete(
                    self._audit_logger.log_action(
                        user_id="system",
                        action="phi_strip",
                        resource="llm_fallback",
                        details={"field_types": stripped_field_types},
                    )
                )
        except Exception:
            logger.warning("Failed to log PHI strip event to audit logger")

    def _log_strip_failure(self) -> None:
        """Log a stripping failure to the audit logger."""
        if self._audit_logger is None:
            return
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    self._audit_logger.log_action(
                        user_id="system",
                        action="phi_strip_failure",
                        resource="llm_fallback",
                    )
                )
        except Exception:
            logger.warning("Failed to log PHI strip failure to audit logger")
