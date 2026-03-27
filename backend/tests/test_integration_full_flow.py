"""
Tests d'intégration — Flux complet Diagno-Pilot
Validates: REQ-01, REQ-02, REQ-03, REQ-09, REQ-10

Flux testé :
  login → création patient → saisie symptômes → diagnostic différentiel
  → prescription → alertes de sécurité → vérification audit log
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from backend.core.config import settings
from backend.routers.auth import create_access_token, hash_password


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_user_doc(role: str = "medecin", password: str = "password123") -> dict:
    oid = ObjectId()
    return {
        "_id": oid,
        "email": "medecin@test.com",
        "password_hash": hash_password(password),
        "role": role,
        "full_name": "Dr. Kofi Mensah",
        "locale": "fr",
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
    }


def _valid_token(user_id: str, role: str = "medecin") -> str:
    return create_access_token(user_id=user_id, role=role)


def _expired_token(user_id: str, role: str = "medecin") -> str:
    expire = datetime.now(timezone.utc) - timedelta(minutes=1)
    import jwt
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _make_mock_db(collections: dict | None = None) -> MagicMock:
    """Build a mock MongoDB database with configurable collections."""
    collections = collections or {}

    def _get_collection(name):
        if name in collections:
            return collections[name]
        col = MagicMock()
        col.find_one = AsyncMock(return_value=None)
        col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
        col.update_one = AsyncMock(return_value=None)
        col.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
        return col

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(side_effect=_get_collection)
    return mock_db


def _make_audit_collection() -> MagicMock:
    col = MagicMock()
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    col.find = MagicMock()
    return col


def _make_diagnoses_json() -> str:
    return json.dumps([
        {"condition": "Paludisme", "probability": 0.80, "icd_code": "B54"},
        {"condition": "Fièvre typhoïde", "probability": 0.60, "icd_code": "A01.0"},
        {"condition": "Dengue", "probability": 0.40, "icd_code": "A90"},
    ])


# ---------------------------------------------------------------------------
# Shared mock context manager for all HTTP tests
# ---------------------------------------------------------------------------

def _patch_all_db(user_doc: dict, audit_col: MagicMock, extra_collections: dict | None = None):
    """
    Returns a context manager that patches all db references used by the app.
    Provides a unified mock DB with user, audit, and optional extra collections.
    """
    user_col = MagicMock()
    user_col.find_one = AsyncMock(return_value=user_doc)
    user_col.update_one = AsyncMock(return_value=None)

    collections = {"users": user_col, "audit_logs": audit_col}
    if extra_collections:
        collections.update(extra_collections)

    mock_db = _make_mock_db(collections)

    class _MultiPatch:
        def __enter__(self):
            self._patches = [
                patch("backend.routers.auth.db"),
                patch("backend.core.auth.db"),
                patch("backend.services.audit_service.db"),
                patch("backend.routers.patients.patient_service.db"),
                patch("backend.routers.diagnose.db"),
                patch("backend.services.patient_service.db"),
            ]
            self._mocks = [p.start() for p in self._patches]
            for m in self._mocks:
                m.get_db.return_value = mock_db
            return mock_db

        def __exit__(self, *args):
            for p in self._patches:
                p.stop()

    return _MultiPatch()


# ---------------------------------------------------------------------------
# 1. Tests d'authentification (REQ-01)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAuthFlow:
    """REQ-01 : Authentification et gestion des rôles."""

    async def test_login_valid_credentials_returns_jwt(self):
        """Login avec identifiants valides retourne un token JWT."""
        from backend.main import app

        user_doc = _make_user_doc(password="password123")
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/auth/login",
                    data={"username": "medecin@test.com", "password": "password123"},
                )

        assert resp.status_code == 200
        body = resp.json()
        # Tokens are now delivered via httpOnly cookies, not in the response body
        assert "access_token" not in body
        assert "refresh_token" not in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0
        # Verify access_token cookie was set
        assert "access_token" in resp.cookies

    async def test_login_wrong_password_returns_401(self):
        """Login avec mauvais mot de passe retourne 401."""
        from backend.main import app

        user_doc = _make_user_doc(password="correctpassword")
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/auth/login",
                    data={"username": "medecin@test.com", "password": "wrongpassword"},
                )

        assert resp.status_code == 401

    async def test_login_unknown_user_returns_401(self):
        """Login avec utilisateur inconnu retourne 401."""
        from backend.main import app

        # user_col returns None (user not found)
        user_col = MagicMock()
        user_col.find_one = AsyncMock(return_value=None)
        audit_col = _make_audit_collection()

        mock_db = _make_mock_db({"users": user_col, "audit_logs": audit_col})

        with patch("backend.routers.auth.db") as m:
            m.get_db.return_value = mock_db
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/auth/login",
                    data={"username": "nobody@test.com", "password": "password123"},
                )

        assert resp.status_code == 401

    async def test_expired_token_returns_401(self):
        """Token expiré retourne 401 sur un endpoint protégé."""
        from backend.main import app

        user_doc = _make_user_doc()
        token = _expired_token(str(user_doc["_id"]))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 401

    async def test_missing_token_returns_401(self):
        """Requête sans token retourne 401."""
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/auth/me")

        assert resp.status_code == 401

    async def test_login_creates_audit_log(self):
        """Un login réussi crée une entrée dans le journal d'audit (REQ-10)."""
        from backend.main import app

        user_doc = _make_user_doc(password="password123")
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post(
                    "/api/v1/auth/login",
                    data={"username": "medecin@test.com", "password": "password123"},
                )

        audit_col.insert_one.assert_called_once()
        call_args = audit_col.insert_one.call_args[0][0]
        assert call_args["action"] == "login"
        assert call_args["resource"] == "auth"
        assert "user_id" in call_args
        assert "created_at" in call_args


# ---------------------------------------------------------------------------
# 2. Tests création patient (REQ-06)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPatientCreation:
    """REQ-06 : Création de profil patient."""

    async def test_create_patient_returns_201(self):
        """POST /api/v1/patients crée un patient et retourne 201."""
        from backend.main import app

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        patient_oid = ObjectId()
        patients_col = MagicMock()
        patients_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=patient_oid))
        patients_col.find_one = AsyncMock(return_value=None)

        with _patch_all_db(user_doc, audit_col, {"patients": patients_col}):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/patients",
                    json={
                        "full_name": "Ama Koffi",
                        "weight_kg": 65.0,
                        "allergies": [],
                        "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                        "current_medications": [],
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 201
        body = resp.json()
        assert body["full_name"] == "Ama Koffi"
        assert body["weight_kg"] == 65.0

    async def test_create_patient_without_token_returns_401(self):
        """POST /api/v1/patients sans token retourne 401."""
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/patients",
                json={"full_name": "Test Patient"},
            )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. Tests diagnostic différentiel (REQ-02)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDiagnoseSymptoms:
    """REQ-02 : Diagnostic différentiel via POST /api/v1/diagnose/symptoms."""

    def _make_rag_mock(self, llm_answer: str | None = None) -> MagicMock:
        """Build a mock DiagnosticService that returns 3 diagnoses."""
        from backend.models.consultation import DifferentialDiagnosis

        diagnoses = [
            DifferentialDiagnosis(condition="Paludisme", probability=0.80, icd_code="B54"),
            DifferentialDiagnosis(condition="Fièvre typhoïde", probability=0.60, icd_code="A01.0"),
            DifferentialDiagnosis(condition="Dengue", probability=0.40, icd_code="A90"),
        ]
        mock_service = MagicMock()
        mock_service.get_differential_diagnosis = AsyncMock(return_value=diagnoses)
        return mock_service

    async def test_diagnose_symptoms_returns_diagnoses(self):
        """POST /api/v1/diagnose/symptoms retourne au moins 3 diagnostics."""
        from backend.main import app
        from backend.routers.diagnose import get_diagnostic_service

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        consultations_col = MagicMock()
        consultations_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

        mock_diag_service = self._make_rag_mock()
        app.dependency_overrides[get_diagnostic_service] = lambda: mock_diag_service

        try:
            with _patch_all_db(user_doc, audit_col, {"consultations": consultations_col}):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post(
                        "/api/v1/diagnose/symptoms",
                        json={
                            "symptoms": [
                                {"name": "fièvre", "severity": "severe", "duration_days": 3},
                                {"name": "céphalées", "severity": "moderate"},
                            ]
                        },
                        headers={"Authorization": f"Bearer {token}"},
                    )
        finally:
            app.dependency_overrides.pop(get_diagnostic_service, None)

        assert resp.status_code == 200
        body = resp.json()
        assert "diagnoses" in body
        assert len(body["diagnoses"]) >= 3
        assert "session_id" in body

    async def test_diagnose_symptoms_have_probability_and_icd(self):
        """Les diagnostics retournés ont des probabilités et des codes CIM-10."""
        from backend.main import app
        from backend.routers.diagnose import get_diagnostic_service

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        consultations_col = MagicMock()
        consultations_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

        mock_diag_service = self._make_rag_mock()
        app.dependency_overrides[get_diagnostic_service] = lambda: mock_diag_service

        try:
            with _patch_all_db(user_doc, audit_col, {"consultations": consultations_col}):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post(
                        "/api/v1/diagnose/symptoms",
                        json={"symptoms": [{"name": "fièvre", "severity": "severe"}]},
                        headers={"Authorization": f"Bearer {token}"},
                    )
        finally:
            app.dependency_overrides.pop(get_diagnostic_service, None)

        assert resp.status_code == 200
        diagnoses = resp.json()["diagnoses"]
        for d in diagnoses:
            assert 0.0 <= d["probability"] <= 1.0
        icd_codes = [d["icd_code"] for d in diagnoses if d.get("icd_code")]
        assert len(icd_codes) >= 1

    async def test_diagnose_symptoms_without_token_returns_401(self):
        """POST /api/v1/diagnose/symptoms sans token retourne 401."""
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/diagnose/symptoms",
                json={"symptoms": [{"name": "fièvre"}]},
            )

        assert resp.status_code == 401

    async def test_diagnose_with_patient_profile(self):
        """POST /api/v1/diagnose/symptoms avec profil patient retourne des diagnostics."""
        from backend.main import app
        from backend.routers.diagnose import get_diagnostic_service

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        consultations_col = MagicMock()
        consultations_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

        mock_diag_service = self._make_rag_mock()
        app.dependency_overrides[get_diagnostic_service] = lambda: mock_diag_service

        try:
            with _patch_all_db(user_doc, audit_col, {"consultations": consultations_col}):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post(
                        "/api/v1/diagnose/symptoms",
                        json={
                            "symptoms": [{"name": "fièvre", "severity": "severe"}],
                            "patient_profile": {
                                "full_name": "Enfant Test",
                                "weight_kg": 20.0,
                                "age_group": "child",
                                "allergies": [],
                                "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                                "current_medications": [],
                            },
                        },
                        headers={"Authorization": f"Bearer {token}"},
                    )
        finally:
            app.dependency_overrides.pop(get_diagnostic_service, None)

        assert resp.status_code == 200
        assert len(resp.json()["diagnoses"]) >= 3


# ---------------------------------------------------------------------------
# 4. Tests prescription + alertes (REQ-03, REQ-09)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPrescriptionAndAlerts:
    """REQ-03 + REQ-09 : Prescription antibiotique et alertes de sécurité."""

    async def test_prescription_safe_patient_no_alerts(self):
        """Prescription pour patient adulte sans risque → 0 alerte."""
        from backend.main import app

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/diagnose/prescription",
                    json={
                        "antibiotic": "amoxicillin",
                        "patient_profile": {
                            "full_name": "Patient Adulte",
                            "weight_kg": 70.0,
                            "age_group": "adult",
                            "allergies": [],
                            "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                            "current_medications": [],
                        },
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["prescription"]["antibiotic"] == "amoxicillin"
        assert body["prescription"]["dose_mg"] > 0
        assert body["prescription"]["frequency"] != ""
        assert body["prescription"]["duration_days"] > 0
        assert body["alerts"] == []

    async def test_prescription_allergy_generates_critical_alert(self):
        """Allergie connue → alerte CRITIQUE avec alternative (REQ-09)."""
        from backend.main import app

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/diagnose/prescription",
                    json={
                        "antibiotic": "ciprofloxacin",
                        "patient_profile": {
                            "full_name": "Patient Allergique",
                            "weight_kg": 65.0,
                            "age_group": "adult",
                            "allergies": ["ciprofloxacin"],
                            "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                            "current_medications": [],
                        },
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        body = resp.json()
        critical_alerts = [a for a in body["alerts"] if a["level"] == "critical" and a["type"] == "allergy"]
        assert len(critical_alerts) >= 1
        assert critical_alerts[0]["alternative"] is not None

    async def test_prescription_child_fluoroquinolone_contraindicated(self):
        """Ciprofloxacine chez l'enfant → alerte CRITIQUE de contre-indication (REQ-09)."""
        from backend.main import app

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/diagnose/prescription",
                    json={
                        "antibiotic": "ciprofloxacin",
                        "patient_profile": {
                            "full_name": "Enfant",
                            "weight_kg": 25.0,
                            "age_group": "child",
                            "allergies": [],
                            "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                            "current_medications": [],
                        },
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        body = resp.json()
        critical = [a for a in body["alerts"] if a["level"] == "critical" and a["type"] == "contraindication"]
        assert len(critical) >= 1
        assert critical[0]["alternative"] is not None

    async def test_prescription_renal_failure_warning_alert(self):
        """Insuffisance rénale → alerte WARNING et dose réduite (REQ-03, REQ-09)."""
        from backend.main import app

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/diagnose/prescription",
                    json={
                        "antibiotic": "amoxicillin",
                        "patient_profile": {
                            "full_name": "Patient IR",
                            "weight_kg": 70.0,
                            "age_group": "adult",
                            "allergies": [],
                            "comorbidities": {"renal_failure": True, "hepatic_failure": False},
                            "current_medications": [],
                        },
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        body = resp.json()
        # Dose should be reduced (3000 * 0.5 = 1500)
        assert body["prescription"]["dose_mg"] == pytest.approx(1500.0)
        warnings = [a for a in body["alerts"] if a["level"] == "warning"]
        assert len(warnings) >= 1

    async def test_prescription_drug_interaction_warning(self):
        """Interaction médicamenteuse connue → alerte WARNING (REQ-09)."""
        from backend.main import app

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/diagnose/prescription",
                    json={
                        "antibiotic": "ciprofloxacin",
                        "patient_profile": {
                            "full_name": "Patient Warfarine",
                            "weight_kg": 70.0,
                            "age_group": "adult",
                            "allergies": [],
                            "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                            "current_medications": ["warfarin"],
                        },
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        body = resp.json()
        interaction_warnings = [a for a in body["alerts"] if a["level"] == "warning" and a["type"] == "interaction"]
        assert len(interaction_warnings) >= 1

    async def test_prescription_unknown_antibiotic_returns_422(self):
        """Antibiotique inconnu → 422 Unprocessable Entity."""
        from backend.main import app

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/diagnose/prescription",
                    json={
                        "antibiotic": "unknown_drug_xyz",
                        "patient_profile": {
                            "full_name": "Patient Test",
                            "weight_kg": 70.0,
                            "age_group": "adult",
                            "allergies": [],
                            "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                            "current_medications": [],
                        },
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 422

    async def test_prescription_without_token_returns_401(self):
        """POST /api/v1/diagnose/prescription sans token retourne 401."""
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/diagnose/prescription",
                json={
                    "antibiotic": "amoxicillin",
                    "patient_profile": {
                        "full_name": "Test",
                        "weight_kg": 70.0,
                        "age_group": "adult",
                        "allergies": [],
                        "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                        "current_medications": [],
                    },
                },
            )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 5. Tests audit log (REQ-10)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAuditLog:
    """REQ-10 : Traçabilité — les actions sensibles créent des entrées d'audit."""

    async def test_audit_log_entry_has_required_fields(self):
        """L'entrée d'audit contient user_id, action, resource, ip_address, created_at."""
        from backend.main import app

        user_doc = _make_user_doc(password="password123")
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post(
                    "/api/v1/auth/login",
                    data={"username": "medecin@test.com", "password": "password123"},
                )

        audit_col.insert_one.assert_called_once()
        entry = audit_col.insert_one.call_args[0][0]
        assert "user_id" in entry
        assert "action" in entry
        assert "resource" in entry
        assert "created_at" in entry
        assert isinstance(entry["created_at"], datetime)

    async def test_audit_log_records_login_action(self):
        """L'action 'login' est enregistrée dans l'audit log."""
        from backend.main import app

        user_doc = _make_user_doc(password="password123")
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post(
                    "/api/v1/auth/login",
                    data={"username": "medecin@test.com", "password": "password123"},
                )

        entry = audit_col.insert_one.call_args[0][0]
        assert entry["action"] == "login"
        assert entry["resource"] == "auth"

    async def test_audit_log_records_logout_action(self):
        """L'action 'logout' est enregistrée dans l'audit log."""
        from backend.main import app

        user_doc = _make_user_doc()
        token = _valid_token(str(user_doc["_id"]))
        audit_col = _make_audit_collection()

        with _patch_all_db(user_doc, audit_col):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post(
                    "/api/v1/auth/logout",
                    headers={"Authorization": f"Bearer {token}"},
                )

        audit_col.insert_one.assert_called_once()
        entry = audit_col.insert_one.call_args[0][0]
        assert entry["action"] == "logout"
        assert entry["resource"] == "auth"
        assert entry["user_id"] == str(user_doc["_id"])


# ---------------------------------------------------------------------------
# 6. Flux complet end-to-end (REQ-01, REQ-02, REQ-03, REQ-09, REQ-10)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestFullFlow:
    """
    Flux complet : login → création patient → diagnostic → prescription → alertes → audit.
    Validates: REQ-01, REQ-02, REQ-03, REQ-09, REQ-10
    """

    async def test_complete_flow_adult_safe_prescription(self):
        """
        Flux complet pour un patient adulte sans risque :
        login → créer patient → diagnostiquer → prescrire → 0 alerte.
        """
        from backend.main import app
        from backend.models.consultation import DifferentialDiagnosis

        user_doc = _make_user_doc(password="password123")
        audit_col = _make_audit_collection()
        patient_oid = ObjectId()

        patients_col = MagicMock()
        patients_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=patient_oid))
        patients_col.find_one = AsyncMock(return_value=None)

        consultations_col = MagicMock()
        consultations_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

        diagnoses = [
            DifferentialDiagnosis(condition="Paludisme", probability=0.80, icd_code="B54"),
            DifferentialDiagnosis(condition="Fièvre typhoïde", probability=0.60, icd_code="A01.0"),
            DifferentialDiagnosis(condition="Dengue", probability=0.40, icd_code="A90"),
        ]
        mock_diag_service = MagicMock()
        mock_diag_service.get_differential_diagnosis = AsyncMock(return_value=diagnoses)

        from backend.routers.diagnose import get_diagnostic_service
        app.dependency_overrides[get_diagnostic_service] = lambda: mock_diag_service

        try:
          with _patch_all_db(user_doc, audit_col, {"patients": patients_col, "consultations": consultations_col}):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

                # Step 1: Login (REQ-01) — tokens now delivered via httpOnly cookies
                login_resp = await client.post(
                    "/api/v1/auth/login",
                    data={"username": "medecin@test.com", "password": "password123"},
                )
                assert login_resp.status_code == 200
                assert "access_token" not in login_resp.json()
                # Cookies are carried automatically by the AsyncClient for subsequent requests

                # Step 2: Create patient (REQ-06)
                patient_resp = await client.post(
                    "/api/v1/patients",
                    json={
                        "full_name": "Kofi Asante",
                        "weight_kg": 70.0,
                        "allergies": [],
                        "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                        "current_medications": [],
                    },
                )
                assert patient_resp.status_code == 201
                assert patient_resp.json()["full_name"] == "Kofi Asante"

                # Step 3: Diagnose symptoms (REQ-02)
                diag_resp = await client.post(
                    "/api/v1/diagnose/symptoms",
                    json={
                        "symptoms": [
                            {"name": "fièvre", "severity": "severe", "duration_days": 3},
                            {"name": "céphalées", "severity": "moderate"},
                        ]
                    },
                )
                assert diag_resp.status_code == 200
                diagnoses_result = diag_resp.json()["diagnoses"]
                assert len(diagnoses_result) >= 3
                # Ordered by descending probability
                probs = [d["probability"] for d in diagnoses_result]
                assert probs == sorted(probs, reverse=True)

                # Step 4: Get prescription + alerts (REQ-03, REQ-09)
                rx_resp = await client.post(
                    "/api/v1/diagnose/prescription",
                    json={
                        "antibiotic": "amoxicillin",
                        "patient_profile": {
                            "full_name": "Kofi Asante",
                            "weight_kg": 70.0,
                            "age_group": "adult",
                            "allergies": [],
                            "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                            "current_medications": [],
                        },
                    },
                )
                assert rx_resp.status_code == 200
                rx_body = rx_resp.json()
                assert rx_body["prescription"]["antibiotic"] == "amoxicillin"
                assert rx_body["prescription"]["dose_mg"] == pytest.approx(3000.0)
                assert rx_body["alerts"] == []
        finally:
            app.dependency_overrides.pop(get_diagnostic_service, None)

        # Step 5: Verify audit log was created for login (REQ-10)
        assert audit_col.insert_one.called
        login_audit = audit_col.insert_one.call_args[0][0]
        assert login_audit["action"] == "login"

    async def test_complete_flow_child_with_allergy(self):
        """
        Flux complet pour un enfant avec allergie à la ciprofloxacine :
        login → diagnostiquer → prescrire → alerte CRITIQUE + alternative.
        """
        from backend.main import app
        from backend.models.consultation import DifferentialDiagnosis

        user_doc = _make_user_doc(password="password123")
        audit_col = _make_audit_collection()

        consultations_col = MagicMock()
        consultations_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

        diagnoses = [
            DifferentialDiagnosis(condition="Paludisme", probability=0.80, icd_code="B54"),
            DifferentialDiagnosis(condition="Fièvre typhoïde", probability=0.60, icd_code="A01.0"),
            DifferentialDiagnosis(condition="Dengue", probability=0.40, icd_code="A90"),
        ]
        mock_diag_service = MagicMock()
        mock_diag_service.get_differential_diagnosis = AsyncMock(return_value=diagnoses)

        from backend.routers.diagnose import get_diagnostic_service
        app.dependency_overrides[get_diagnostic_service] = lambda: mock_diag_service

        try:
          with _patch_all_db(user_doc, audit_col, {"consultations": consultations_col}):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

                # Step 1: Login — tokens now delivered via httpOnly cookies
                login_resp = await client.post(
                    "/api/v1/auth/login",
                    data={"username": "medecin@test.com", "password": "password123"},
                )
                assert login_resp.status_code == 200
                assert "access_token" not in login_resp.json()
                # Cookies are carried automatically by the AsyncClient for subsequent requests

                # Step 2: Diagnose symptoms for child
                diag_resp = await client.post(
                    "/api/v1/diagnose/symptoms",
                    json={
                        "symptoms": [{"name": "fièvre", "severity": "severe"}],
                        "patient_profile": {
                            "full_name": "Enfant Allergique",
                            "weight_kg": 25.0,
                            "age_group": "child",
                            "allergies": ["ciprofloxacin"],
                            "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                            "current_medications": [],
                        },
                    },
                )
                assert diag_resp.status_code == 200
                assert len(diag_resp.json()["diagnoses"]) >= 3

                # Step 3: Prescription — ciprofloxacin contraindicated for child + allergy
                rx_resp = await client.post(
                    "/api/v1/diagnose/prescription",
                    json={
                        "antibiotic": "ciprofloxacin",
                        "patient_profile": {
                            "full_name": "Enfant Allergique",
                            "weight_kg": 25.0,
                            "age_group": "child",
                            "allergies": ["ciprofloxacin"],
                            "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                            "current_medications": [],
                        },
                    },
                )
                assert rx_resp.status_code == 200
                rx_body = rx_resp.json()
                critical_alerts = [
                    a for a in rx_body["alerts"]
                    if a["level"] == "critical"
                ]
                assert len(critical_alerts) >= 1
                # At least one critical alert should propose an alternative
                alternatives = [a["alternative"] for a in critical_alerts if a.get("alternative")]
                assert len(alternatives) >= 1
        finally:
            app.dependency_overrides.pop(get_diagnostic_service, None)

        # Audit log created for login
        assert audit_col.insert_one.called

    async def test_complete_flow_auth_failure_blocks_access(self):
        """
        Flux d'échec d'authentification : token invalide bloque l'accès aux endpoints protégés.
        """
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # All protected endpoints should return 401 without a valid token
            for endpoint, method, payload in [
                ("/api/v1/patients", "POST", {"full_name": "Test"}),
                ("/api/v1/diagnose/symptoms", "POST", {"symptoms": [{"name": "fièvre"}]}),
                ("/api/v1/diagnose/prescription", "POST", {
                    "antibiotic": "amoxicillin",
                    "patient_profile": {
                        "full_name": "Test", "weight_kg": 70.0, "age_group": "adult",
                        "allergies": [], "comorbidities": {"renal_failure": False, "hepatic_failure": False},
                        "current_medications": [],
                    },
                }),
            ]:
                if method == "POST":
                    resp = await client.post(endpoint, json=payload)
                else:
                    resp = await client.get(endpoint)
                assert resp.status_code == 401, f"Expected 401 for {method} {endpoint}, got {resp.status_code}"
