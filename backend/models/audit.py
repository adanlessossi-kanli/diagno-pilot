from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AuditLog(BaseModel):
    """
    Entrée du journal d'audit.

    Champs obligatoires pour la traçabilité (Requirements 4.3, 5.4) :
      - user_id    : identifiant de l'utilisateur ayant effectué l'action
      - timestamp  : horodatage UTC de l'action (alias de created_at)
      - ip_address : adresse IP du client
    """

    id: str | None = None
    user_id: str
    action: str
    resource: str
    resource_id: str | None = None
    details: dict = {}
    ip_address: str | None = None
    # `created_at` est l'horodatage de l'entrée — toujours renseigné par audit_service
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def timestamp(self) -> datetime:
        """Alias pour created_at — horodatage de l'entrée d'audit."""
        return self.created_at


class HIPAAAuditRecord(BaseModel):
    """Entrée de journal d'audit HIPAA avec chaîne de hachage anti-falsification.

    Chaque enregistrement inclut le hash de l'enregistrement précédent pour
    garantir l'intégrité de la chaîne (Requirement 8.6).

    Validates: Requirements 8.1
    """

    id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str
    action: str  # phi_read | phi_write | phi_delete | llm_request | phi_strip
    resource: str
    resource_id: str | None = None
    details: dict = {}
    ip_address: str | None = None
    previous_hash: str = ""  # hash of previous record (empty string for first)
    record_hash: str = ""  # SHA-256(previous_hash + json(record_without_hashes))
