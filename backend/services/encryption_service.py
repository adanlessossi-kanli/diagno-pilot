"""
Service de chiffrement AES-256-GCM pour les champs PHI — Diagno-Pilot

Fournit le chiffrement/déchiffrement au niveau des champs pour les données
PHI stockées dans MongoDB, avec support de rotation de clés.

Migration Fernet → AES-256-GCM :
- Le chiffrement utilise désormais AES-256-GCM (nonce 12 octets, tag 16 octets).
- Le déchiffrement tente d'abord AES-256-GCM, puis Fernet en fallback
  pour les données chiffrées avant la migration.
- Les tokens Fernet commencent par ``gAAAAA`` (base64 standard).

Génération d'une clé AES-256-GCM compatible ::

    python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.services.phi_classifier import PHIClassifier

logger = logging.getLogger(__name__)

_NONCE_SIZE = 12  # 96-bit nonce recommended for AES-GCM


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""


class EncryptionService:
    """AES-256-GCM field-level encryption for PHI data.

    Accepts a 32-byte key encoded as URL-safe base64.  Each encryption
    generates a random 12-byte nonce.  Ciphertext format::

        base64url( nonce[12] || ciphertext+tag )

    Backward-compatible: decryption falls back to Fernet for legacy data
    (tokens starting with ``gAAAAA``).

    Key generation::

        python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    """

    def __init__(self, key: str | None = None, audit_logger: Any | None = None):
        """Initialise with a base64url-encoded 32-byte AES-256 key.

        Parameters
        ----------
        key:
            A URL-safe base64-encoded 32-byte key.  If *None*, a new random
            key is generated (useful for tests).
        audit_logger:
            Optional audit logger instance for recording failures.

        Raises
        ------
        ValueError
            If the decoded key is not exactly 32 bytes.
        """
        if key is None:
            raw = os.urandom(32)
            key = base64.urlsafe_b64encode(raw).decode()
        else:
            raw = base64.urlsafe_b64decode(key)
            if len(raw) != 32:
                raise ValueError(
                    f"AES-256-GCM key must be exactly 32 bytes, got {len(raw)}"
                )

        self._key = key
        self._aesgcm = AESGCM(raw)
        self._previous_aesgcm: AESGCM | None = None
        self._previous_fernet: Fernet | None = None
        self._audit_logger = audit_logger

    # ------------------------------------------------------------------
    # Single-field operations
    # ------------------------------------------------------------------

    def encrypt_field(self, plaintext: str) -> str:
        """Encrypt *plaintext* and return a base64url-encoded ciphertext string.

        Format: ``base64url(nonce[12] || ciphertext+tag)``
        """
        try:
            nonce = os.urandom(_NONCE_SIZE)
            ct = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
            return base64.urlsafe_b64encode(nonce + ct).decode("ascii")
        except Exception:
            self._log_failure("encrypt_field")
            raise EncryptionError("Encryption failed")

    def decrypt_field(self, ciphertext: str) -> str:
        """Decrypt *ciphertext* and return the original plaintext string.

        Tries AES-256-GCM first (current key, then previous key), then
        falls back to Fernet for legacy data.
        """
        # --- Try AES-256-GCM with current key ---
        try:
            raw = base64.urlsafe_b64decode(ciphertext)
            nonce, ct = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
            return self._aesgcm.decrypt(nonce, ct, None).decode("utf-8")
        except Exception:
            pass

        # --- Try AES-256-GCM with previous key (rotation window) ---
        if self._previous_aesgcm is not None:
            try:
                raw = base64.urlsafe_b64decode(ciphertext)
                nonce, ct = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
                return self._previous_aesgcm.decrypt(nonce, ct, None).decode("utf-8")
            except Exception:
                pass

        # --- Fernet fallback for legacy data ---
        if self._previous_fernet is not None:
            try:
                return self._previous_fernet.decrypt(
                    ciphertext.encode("ascii")
                ).decode("utf-8")
            except (InvalidToken, Exception):
                pass

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
        """Rotate to *new_key*, keeping the old key for decryption fallback.

        The previous AES-GCM key is stored for the rotation window.
        Any existing Fernet fallback is preserved for legacy data.
        """
        self._previous_aesgcm = self._aesgcm
        self._key = new_key
        raw = base64.urlsafe_b64decode(new_key)
        self._aesgcm = AESGCM(raw)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_failure(self, operation: str) -> None:
        """Log encryption/decryption failure without exposing plaintext."""
        logger.error("EncryptionService.%s failed", operation)
        if self._audit_logger is not None:
            try:
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
