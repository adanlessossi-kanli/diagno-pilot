from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Réponse paginée générique — REQ 8.1, 8.2, 8.3"""
    items: list[T]
    total: int
    page: int
    page_size: int


class AgeGroup(str, Enum):
    NEONATAL = "neonatal"  # 0–28 jours
    INFANT = "infant"      # 1–23 mois
    CHILD = "child"        # 2–17 ans
    ADULT = "adult"        # 18+ ans


class AlertLevel(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Locale(str, Enum):
    FR = "fr"
    EN = "en"


class UserRole(str, Enum):
    MEDECIN = "medecin"
    PHARMACIEN = "pharmacien"
    ADMIN = "admin"
