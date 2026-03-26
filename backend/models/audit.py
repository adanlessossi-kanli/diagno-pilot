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
