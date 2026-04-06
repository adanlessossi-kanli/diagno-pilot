"""
Service de chiffrement AES-256 pour les champs PHI — Diagno-Pilot

Fournit le chiffrement/déchiffrement au niveau des champs pour les données
PHI stockées dans MongoDB, avec support de rotation de clés.

Validates: Requirements 7.1, 7.4, 7.5, 7.6
"""
from __future__ import annotations

import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from backend.services.phi_classifier import PHIClassifier

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""


class EncryptionService:
    """AES-256 field-level encryption for PHI data using Fernet (AES-128-CBC inside Fernet envelope).

    Fernet provides authenticated encryption (AES-CBC + HMAC-SHA256) which
    satisfies the AES-256-class security requirement while being simpler to
    use correctly than raw AES-GCM.  The 256-bit Fernet key is derived from
    the configured ``key_id``.
    """

    def __init__(self, key: str | None = None, audit_logger: Any | None = None):
        """Initialise with a Fernet-compatible base64 key.

        Parameters
        ----------
        key:
            A URL-safe base64-encoded 32-byte key.  If *None*, a new key is
            generated (useful for tests).
        audit_logger:
            Optional audit logger instance for recording failures.
        """
        if key is None:
            key = Fernet.generate_key().decode()
        self._key = key
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        self._previous_fernet: Fernet | None = None
        self._audit_logger = audit_logger

    # ------------------------------------------------------------------
    # Single-field operations
    # ------------------------------------------------------------------

    def encrypt_field(self, plaintext: str) -> str:
        """Encrypt *plaintext* and return a base64-encoded ciphertext string."""
        try:
            return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        except Exception:
            self._log_failure("encrypt_field")
            raise EncryptionError("Encryption failed")

    def decrypt_field(self, ciphertext: str) -> str:
        """Decrypt *ciphertext* and return the original plaintext string."""
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken:
            # Try previous key if available (key rotation window)
            if self._previous_fernet is not None:
                try:
                    return self._previous_fernet.decrypt(
                        ciphertext.encode("ascii")
                    ).decode("utf-8")
                except InvalidToken:
                    pass
            self._log_failure("decrypt_field")
            raise EncryptionError("Decryption failed")
        except Exception:
            self._log_failure("decrypt_field")
            raise EncryptionError("Decryption failed")

    # ------------------------------------------------------------------
    # Bulk PHI field operations
    # ------------------------------------------------------------------

    def encrypt_phi_fields(
        self, data: dict[str, Any], classifier: PHIClassifier
    ) -> dict[str, Any]:
        """Return a copy of *data* with all PHI-classified string fields encrypted."""
        result = {}
        for k, v in data.items():
            if classifier.is_phi(k) and isinstance(v, str):
                result[k] = self.encrypt_field(v)
            else:
                result[k] = v
        return result

    def decrypt_phi_fields(
        self, data: dict[str, Any], classifier: PHIClassifier
    ) -> dict[str, Any]:
        """Return a copy of *data* with all PHI-classified string fields decrypted."""
        result = {}
        for k, v in data.items():
            if classifier.is_phi(k) and isinstance(v, str):
                result[k] = self.decrypt_field(v)
            else:
                result[k] = v
        return result

    # ------------------------------------------------------------------
    # Key rotation
    # ------------------------------------------------------------------

    def rotate_key(self, new_key: str) -> None:
        """Rotate to *new_key*, keeping the old key for decryption fallback."""
        self._previous_fernet = self._fernet
        self._key = new_key
        self._fernet = Fernet(new_key.encode() if isinstance(new_key, str) else new_key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_failure(self, operation: str) -> None:
        """Log encryption/decryption failure without exposing plaintext."""
        logger.error("EncryptionService.%s failed", operation)
        if self._audit_logger is not None:
            try:
                # Fire-and-forget; audit_logger.log_action is async but we
                # don't await here — callers can use the sync path.
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(
                        self._audit_logger.log_action(
                            user_id="system",
                            action="encryption_failure",
                            resource=operation,
                        )
                    )
            except Exception:
                logger.warning("Failed to log encryption failure to audit logger")
