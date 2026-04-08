"""
Service de classification PHI — Diagno-Pilot

Classifie les champs de données comme PHI (Protected Health Information)
ou non-PHI pour le chiffrement et le contrôle d'accès.

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
"""
from __future__ import annotations

from typing import Any


class PHIClassifier:
    """Classifie les champs de données comme PHI ou non-PHI.

    Les champs inconnus sont classifiés comme PHI par défaut (Req 6.5).
    """

    PHI_FIELDS: frozenset[str] = frozenset({
        "full_name",
        "date_of_birth",
        "medical_record_number",
        "allergies",
        "current_medications",
        "comorbidities",
        "weight_kg",
        "diagnoses",
        "prescriptions",
        "consultation_notes",
        "differential_diagnoses",
        "partial_differential",
    })

    NON_PHI_FIELDS: frozenset[str] = frozenset({
        "age_group",
        "created_by",
        "created_at",
        "updated_at",
        "confidence_score",
        "locale",
        "region",
        "fallback_used",
        "source",
        "document_type",
        "evidence_level",
        "disease_tags",
    })

    def is_phi(self, field_name: str) -> bool:
        """Return True if *field_name* is classified as PHI.

        Known PHI fields → True.
        Known non-PHI fields → False.
        Unknown fields → True (safe default per Req 6.5).
        """
        if field_name in self.PHI_FIELDS:
            return True
        if field_name in self.NON_PHI_FIELDS:
            return False
        # Unknown fields default to PHI
        return True

    def classify_document(self, data: dict[str, Any]) -> dict[str, bool]:
        """Return ``{field_name: is_phi}`` for every key in *data*."""
        return {k: self.is_phi(k) for k in data}

    def extract_phi_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return only the PHI-classified entries from *data*."""
        return {k: v for k, v in data.items() if self.is_phi(k)}

    def extract_non_phi_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return only the non-PHI entries from *data*."""
        return {k: v for k, v in data.items() if not self.is_phi(k)}


# Module-level singleton
phi_classifier = PHIClassifier()
