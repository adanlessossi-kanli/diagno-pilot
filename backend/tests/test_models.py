"""
Tests de validation des modèles Pydantic — Diagno-Pilot
Validates: Requirements REQ-06, REQ-08
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from backend.models import (
    AuditLog,
    DifferentialDiagnosis,
    PatientCreate,
    PatientProfile,
    Prescription,
    SafetyAlert,
    UserCreate,
)
from backend.models.common import AlertLevel, UserRole


# ---------------------------------------------------------------------------
# PatientProfile
# ---------------------------------------------------------------------------

class TestPatientProfile:
    def test_valid_full(self):
        p = PatientProfile(
            full_name="Alice Dupont",
            date_of_birth=date(1990, 5, 15),
            weight_kg=65.0,
            allergies=["pénicilline"],
        )
        assert p.full_name == "Alice Dupont"
        assert p.weight_kg == 65.0

    def test_weight_negative_raises(self):
        with pytest.raises(ValidationError):
            PatientProfile(full_name="X", weight_kg=-1.0)

    def test_weight_zero_raises(self):
        with pytest.raises(ValidationError):
            PatientProfile(full_name="X", weight_kg=0.0)

    def test_weight_positive_ok(self):
        p = PatientProfile(full_name="X", weight_kg=0.001)
        assert p.weight_kg == pytest.approx(0.001)

    def test_date_of_birth_valid(self):
        p = PatientProfile(full_name="X", date_of_birth=date(2000, 1, 1))
        assert p.date_of_birth == date(2000, 1, 1)

    def test_allergies_default_empty(self):
        p = PatientProfile(full_name="X")
        assert p.allergies == []


# ---------------------------------------------------------------------------
# PatientCreate
# ---------------------------------------------------------------------------

class TestPatientCreate:
    def test_valid_minimal(self):
        p = PatientCreate(full_name="Bob Martin")
        assert p.full_name == "Bob Martin"
        assert p.weight_kg is None

    def test_weight_negative_raises(self):
        with pytest.raises(ValidationError):
            PatientCreate(full_name="X", weight_kg=-5.0)


# ---------------------------------------------------------------------------
# Prescription
# ---------------------------------------------------------------------------

class TestPrescription:
    def test_valid(self):
        rx = Prescription(
            antibiotic="Amoxicilline",
            dose_mg=500.0,
            frequency="3x/jour",
            duration_days=7,
            route="oral",
        )
        assert rx.is_capped_to_adult_dose is False

    def test_dose_zero_raises(self):
        with pytest.raises(ValidationError):
            Prescription(
                antibiotic="X", dose_mg=0.0,
                frequency="1x/jour", duration_days=5, route="oral",
            )

    def test_dose_negative_raises(self):
        with pytest.raises(ValidationError):
            Prescription(
                antibiotic="X", dose_mg=-10.0,
                frequency="1x/jour", duration_days=5, route="oral",
            )

    def test_duration_zero_raises(self):
        with pytest.raises(ValidationError):
            Prescription(
                antibiotic="X", dose_mg=100.0,
                frequency="1x/jour", duration_days=0, route="oral",
            )

    def test_duration_negative_raises(self):
        with pytest.raises(ValidationError):
            Prescription(
                antibiotic="X", dose_mg=100.0,
                frequency="1x/jour", duration_days=-3, route="oral",
            )

    def test_is_capped_default_false(self):
        rx = Prescription(
            antibiotic="X", dose_mg=250.0,
            frequency="2x/jour", duration_days=10, route="IV",
        )
        assert rx.is_capped_to_adult_dose is False


# ---------------------------------------------------------------------------
# DifferentialDiagnosis
# ---------------------------------------------------------------------------

class TestDifferentialDiagnosis:
    def test_probability_above_one_raises(self):
        with pytest.raises(ValidationError):
            DifferentialDiagnosis(condition="Grippe", probability=1.1)

    def test_probability_negative_raises(self):
        with pytest.raises(ValidationError):
            DifferentialDiagnosis(condition="Grippe", probability=-0.1)

    def test_probability_zero_ok(self):
        d = DifferentialDiagnosis(condition="Grippe", probability=0.0)
        assert d.probability == 0.0

    def test_probability_one_ok(self):
        d = DifferentialDiagnosis(condition="Grippe", probability=1.0)
        assert d.probability == 1.0

    def test_probability_mid_ok(self):
        d = DifferentialDiagnosis(condition="Grippe", probability=0.75)
        assert d.probability == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# SafetyAlert
# ---------------------------------------------------------------------------

class TestSafetyAlert:
    def test_valid_critical(self):
        alert = SafetyAlert(
            level=AlertLevel.CRITICAL,
            type="allergy",
            message="Allergie à la pénicilline détectée",
            affected_drug="Amoxicilline",
        )
        assert alert.level == AlertLevel.CRITICAL
        assert alert.alternative is None

    def test_alternative_optional(self):
        alert = SafetyAlert(
            level=AlertLevel.WARNING,
            type="interaction",
            message="Interaction possible",
            alternative="Azithromycine",
        )
        assert alert.alternative == "Azithromycine"


# ---------------------------------------------------------------------------
# UserCreate
# ---------------------------------------------------------------------------

class TestUserCreate:
    def test_password_too_short_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="doc@example.com",
                password="abc123",
                role=UserRole.MEDECIN,
                full_name="Dr. Test",
            )

    def test_password_exactly_8_ok(self):
        u = UserCreate(
            email="doc@example.com",
            password="abcd1234",
            role=UserRole.MEDECIN,
            full_name="Dr. Test",
        )
        assert len(u.password) == 8

    def test_password_long_ok(self):
        u = UserCreate(
            email="doc@example.com",
            password="test_password_123",
            role=UserRole.MEDECIN,
            full_name="Dr. Test",
        )
        assert u.password == "test_password_123"

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="not-an-email",
                password="abcd1234",
                role=UserRole.MEDECIN,
                full_name="Dr. Test",
            )


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_valid(self):
        log = AuditLog(
            user_id="user-1",
            action="login",
            resource="auth",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        assert log.user_id == "user-1"

    def test_details_default_empty(self):
        log = AuditLog(user_id="u", action="read", resource="patient")
        assert log.details == {}


# ---------------------------------------------------------------------------
# Property-based tests (hypothesis)
# ---------------------------------------------------------------------------

@given(w=st.floats(min_value=1e-9, max_value=1e6, allow_nan=False, allow_infinity=False))
@settings(max_examples=200)
def test_property_patient_weight_positive(w):
    """
    Validates: Requirements REQ-06, REQ-08
    Propriété PatientProfile.weight_kg : pour tout float > 0,
    PatientProfile(full_name="X", weight_kg=w) est valide.
    """
    p = PatientProfile(full_name="X", weight_kg=w)
    assert p.weight_kg == pytest.approx(w)


@given(p=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=200)
def test_property_differential_probability_valid(p):
    """
    Validates: Requirements REQ-02
    Propriété DifferentialDiagnosis.probability : pour tout float dans [0, 1],
    la création est valide.
    """
    d = DifferentialDiagnosis(condition="Test", probability=p)
    assert 0.0 <= d.probability <= 1.0


@given(
    p=st.one_of(
        st.floats(max_value=-1e-9, allow_nan=False, allow_infinity=False),
        st.floats(min_value=1.0 + 1e-9, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
)
@settings(max_examples=200)
def test_property_differential_probability_invalid(p):
    """
    Validates: Requirements REQ-02
    Propriété DifferentialDiagnosis.probability : pour tout float hors [0, 1],
    ValidationError est levée.
    """
    with pytest.raises(ValidationError):
        DifferentialDiagnosis(condition="Test", probability=p)
