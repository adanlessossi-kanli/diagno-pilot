from enum import Enum


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
