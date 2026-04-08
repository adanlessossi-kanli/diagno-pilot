"""Unit tests for MCP integration endpoints and DiagnosticOrchestrator.

Tests:
  1. Infirmière can access POST /api/v1/diagnose/symptoms (HTTP 200)
  2. Infirmière can access GET /api/v1/consultations/me (HTTP 200)
  3. Infirmière cannot access GET /api/v1/admin/users (HTTP 403)
  4. MCP consultation auto-created with patient_id
  5. MCP consultation auto-created without patient_id (is_one_shot=True)
  6. Consultation write failure does not block the diagnostic request
  7. Audit write failure does not block the diagnostic request

Requirements: 7.3, 10.1, 10.2, 11.3, 11.4, 11.11, 13.2, 13.3
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from backend.models.consultation import DifferentialDiagnosis, Symptom
from backend.services.diagnostic_service import DiagnosticOrchestrator, DiagnosticResult
from backend.services.mcp_host import AgentResult, DiagnosticAuditData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_OID = ObjectId()

_INFIRMIERE_USER = {
    "_id": _USER_OID,
    "email": "nurse@example.com",
    "role": "infirmière",
    "full_name": "Test Nurse",
    "is_active": True,
}

_CSRF_TOKEN = "test-csrf-token"


def _make_agent_result(name: str = "epidemiology") -> AgentResult:
    return AgentResult(
        agent_name=name,
        sub_question="test question",
        chunks=[{"document_id": "d1", "title": "t1", "source": "s1", "excerpt": "e1", "page": 1}],
        confidence_score=0.8,
        partial_differential=[
            DifferentialDiagnosis(condition="Malaria", probability=0.9, icd_code="B54"),
            DifferentialDiagnosis(condition="Dengue", probability=0.5, icd_code="A90"),
            DifferentialDiagnosis(condition="Typhoid", probability=0.3, icd_code="A01"),
        ],
    )


def _make_audit_data() -> DiagnosticAuditData:
    return DiagnosticAuditData(timeouts=[], omissions=[], agent_results=[])


def _make_diagnostic_result() -> DiagnosticResult:
    return DiagnosticResult(
        diagnoses=[
            DifferentialDiagnosis(condition="Malaria", probability=0.9, icd_code="B54"),
            DifferentialDiagnosis(condition="Dengue", probability=0.5, icd_code="A90"),
            DifferentialDiagnosis(condition="Typhoid", probability=0.3, icd_code="A01"),
        ],
        fallback_used=False,
        degraded_warning=None,
        locale="fr-TG",
        session_id="test-session-id",
        confidence_score=0.8,
        evidence_citations=[],
        agent_contributions=[],
    )


def _make_mock_rag():
    """Create a minimal mock RAG service for DiagnosticOrchestrator init."""
    from backend.services.llamaindex_pipeline import RAGResponse

    mock_rag = MagicMock()
    mock_rag.query = AsyncMock(return_value=RAGResponse(
        answer='[{"condition": "Malaria", "probability": 0.9, "icd_code": "B54"}, '
               '{"condition": "Dengue", "probability": 0.5, "icd_code": "A90"}, '
               '{"condition": "Typhoid", "probability": 0.3, "icd_code": "A01"}]',
        sources=[],
        llm_used="test-model",
        fallback_used=False,
    ))
    return mock_rag


# ---------------------------------------------------------------------------
# Test 1: Infirmière can access POST /api/v1/diagnose/symptoms
# Validates: Requirements 10.1, 13.2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_infirmiere_can_access_diagnose_endpoint():
    """Infirmière role can call POST /api/v1/diagnose/symptoms and get HTTP 200."""
    from backend.main import app
    from backend.core.auth import get_current_user
    from backend.routers.diagnose import get_diagnostic_service
    from backend.core.rate_limit import limiter

    mock_service = AsyncMock()
    mock_service.get_differential_diagnosis = AsyncMock(return_value=_make_diagnostic_result())

    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    app.dependency_overrides[get_current_user] = lambda: _INFIRMIERE_USER
    app.dependency_overrides[get_diagnostic_service] = lambda: mock_service

    original_enabled = limiter.enabled
    limiter.enabled = False
    try:
        with patch("backend.routers.diagnose.db") as patched_db:
            patched_db.get_db.return_value = mock_db
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                cookies={"csrf_token": _CSRF_TOKEN},
            ) as client:
                response = await client.post(
                    "/api/v1/diagnose/symptoms",
                    json={"symptoms": [{"name": "fever", "severity": "moderate", "duration_days": 3}]},
                    headers={"X-CSRF-Token": _CSRF_TOKEN},
                )
    finally:
        limiter.enabled = original_enabled
        app.dependency_overrides.clear()

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test 2: Infirmière can access GET /api/v1/consultations/me
# Validates: Requirements 10.1, 13.2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_infirmiere_can_access_consultations_me_endpoint():
    """Infirmière role can call GET /api/v1/consultations/me and get HTTP 200."""
    from backend.main import app
    from backend.core.auth import get_current_user
    from backend.core.rate_limit import limiter

    app.dependency_overrides[get_current_user] = lambda: _INFIRMIERE_USER

    mock_list = AsyncMock(return_value=([], 0))

    original_enabled = limiter.enabled
    limiter.enabled = False
    try:
        with patch("backend.routers.consultations.consultation_service") as mock_cs:
            mock_cs.list_my_consultations = mock_list
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/api/v1/consultations/me")
    finally:
        limiter.enabled = original_enabled
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# Test 3: Infirmière cannot access admin endpoints (HTTP 403)
# Validates: Requirements 10.2, 13.3
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_infirmiere_cannot_access_admin_endpoints():
    """Infirmière role gets HTTP 403 when accessing GET /api/v1/admin/users."""
    from backend.main import app
    from backend.core.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _INFIRMIERE_USER

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/admin/users")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Test 4: MCP consultation auto-created with patient_id
# Validates: Requirements 11.3, 11.4
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_consultation_auto_created_with_patient_id():
    """When patient_id is provided, consultation is created with patient_id set and is_one_shot=False."""
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock()

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    orchestrator = DiagnosticOrchestrator(
        rag_service=_make_mock_rag(),
        mcp_host=MagicMock(),
        db=mock_db,
    )

    result = _make_diagnostic_result()
    symptoms = [Symptom(name="fever")]

    await orchestrator._create_mcp_consultation(
        mcp_session_id="session-1",
        user_id="user-1",
        symptoms=symptoms,
        result=result,
        patient_id="patient123",
    )

    mock_collection.insert_one.assert_called_once()
    inserted_doc = mock_collection.insert_one.call_args.args[0]
    assert inserted_doc["patient_id"] == "patient123"
    assert inserted_doc["is_one_shot"] is False


# ---------------------------------------------------------------------------
# Test 5: MCP consultation auto-created without patient_id
# Validates: Requirements 11.3, 11.4
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_consultation_auto_created_without_patient_id():
    """When patient_id is None, consultation is created with patient_id=None and is_one_shot=True."""
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock()

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    orchestrator = DiagnosticOrchestrator(
        rag_service=_make_mock_rag(),
        mcp_host=MagicMock(),
        db=mock_db,
    )

    result = _make_diagnostic_result()
    symptoms = [Symptom(name="fever")]

    await orchestrator._create_mcp_consultation(
        mcp_session_id="session-2",
        user_id="user-1",
        symptoms=symptoms,
        result=result,
        patient_id=None,
    )

    mock_collection.insert_one.assert_called_once()
    inserted_doc = mock_collection.insert_one.call_args.args[0]
    assert inserted_doc["patient_id"] is None
    assert inserted_doc["is_one_shot"] is True


# ---------------------------------------------------------------------------
# Test 6: Consultation write failure does not block the request
# Validates: Requirements 11.11
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consultation_write_failure_does_not_block_request():
    """When db['consultations'].insert_one raises, _get_diagnosis_via_mcp still returns a valid result."""
    mock_consult_collection = MagicMock()
    mock_consult_collection.insert_one = AsyncMock(side_effect=Exception("DB write failed"))

    mock_audit_collection = MagicMock()
    mock_audit_collection.insert_one = AsyncMock()

    mock_db = MagicMock()

    def _getitem(name):
        if name == "consultations":
            return mock_consult_collection
        if name == "diagnostic_audit":
            return mock_audit_collection
        return MagicMock()

    mock_db.__getitem__ = MagicMock(side_effect=_getitem)

    mock_mcp_host = AsyncMock()
    agent_results = [_make_agent_result("epidemiology")]
    audit_data = _make_audit_data()
    mock_mcp_host.run_diagnostic = AsyncMock(return_value=(agent_results, audit_data))

    orchestrator = DiagnosticOrchestrator(
        rag_service=_make_mock_rag(),
        mcp_host=mock_mcp_host,
        db=mock_db,
    )

    symptoms = [Symptom(name="fever")]
    result = await orchestrator._get_diagnosis_via_mcp(
        symptoms=symptoms,
        patient_profile=None,
        locale="fr-TG",
        region=None,
        user_id="user-1",
    )

    assert isinstance(result, DiagnosticResult)
    assert len(result.diagnoses) >= 3
    assert result.session_id is not None


# ---------------------------------------------------------------------------
# Test 7: Audit write failure does not block the request
# Validates: Requirements 7.3
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_write_failure_does_not_block_request():
    """When db['diagnostic_audit'].insert_one raises, get_differential_diagnosis still returns a valid result."""
    mock_consult_collection = MagicMock()
    mock_consult_collection.insert_one = AsyncMock()

    mock_audit_collection = MagicMock()
    mock_audit_collection.insert_one = AsyncMock(side_effect=Exception("Audit write failed"))

    mock_db = MagicMock()

    def _getitem(name):
        if name == "consultations":
            return mock_consult_collection
        if name == "diagnostic_audit":
            return mock_audit_collection
        return MagicMock()

    mock_db.__getitem__ = MagicMock(side_effect=_getitem)

    mock_mcp_host = AsyncMock()
    agent_results = [_make_agent_result("epidemiology")]
    audit_data = _make_audit_data()
    mock_mcp_host.run_diagnostic = AsyncMock(return_value=(agent_results, audit_data))

    orchestrator = DiagnosticOrchestrator(
        rag_service=_make_mock_rag(),
        mcp_host=mock_mcp_host,
        db=mock_db,
    )

    symptoms = [Symptom(name="fever")]
    result = await orchestrator.get_differential_diagnosis(
        symptoms=symptoms,
        patient_profile=None,
        locale="fr-TG",
        region=None,
        user_id="user-1",
    )

    # Audit write failure must not prevent a valid diagnostic result
    assert isinstance(result, DiagnosticResult)
    assert len(result.diagnoses) >= 3
