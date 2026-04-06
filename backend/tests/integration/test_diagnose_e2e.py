"""
Backend E2E diagnose and prescription integration tests — real MongoDB via Testcontainers.

Feature: testing-coverage
Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
"""
from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import AsyncClient, ASGITransport
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Stub LLM response — 3 valid differential diagnoses
# ---------------------------------------------------------------------------

_STUB_DIAGNOSES = [
    {"condition": "Paludisme", "probability": 0.85, "icd_code": "B54"},
    {"condition": "Fièvre typhoïde", "probability": 0.70, "icd_code": "A01.0"},
    {"condition": "Méningite bactérienne", "probability": 0.55, "icd_code": "G00.9"},
]

_STUB_DIAGNOSES_JSON = json.dumps(_STUB_DIAGNOSES)

# OpenAI-compatible stub response for chat/completions
_STUB_CHAT_RESPONSE = {
    "choices": [{"message": {"content": _STUB_DIAGNOSES_JSON}}]
}

# OpenAI-compatible stub response for embeddings
_STUB_EMBEDDING_RESPONSE = {
    "data": [{"embedding": [0.0] * 1536}]
}

# LLM base URL used in tests (must match what the service will call)
_LLM_BASE_URL = "https://api.openai.com/v1"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def medecin_client(integration_app):
    """Async client authenticated as the seeded medecin user."""
    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "medecin@test.local", "password": "TestPassword123!"},
        )
        assert resp.status_code == 200, f"medecin login failed: {resp.text}"
        yield client


def _setup_diagnostic_service(integration_app):
    """
    Attach a real DiagnosticService to app.state, configured to call
    _LLM_BASE_URL so that respx can intercept the requests.
    """
    from backend.services.diagnostic_service import DiagnosticService
    from backend.services.embedding_model import EmbeddingModel
    from backend.services.llm_router import LLMRouter
    from backend.services.index_manager import IndexManager
    from backend.services.llamaindex_pipeline import LlamaIndexPipeline
    from motor.motor_asyncio import AsyncIOMotorClient

    # Use the same LLM base URL so respx can intercept the requests
    llm_router = LLMRouter(
        primary_url=_LLM_BASE_URL,
        primary_api_key="test-key",
        fallback_url=_LLM_BASE_URL,
        fallback_api_key="test-key",
    )
    embedder = EmbeddingModel(
        base_url=_LLM_BASE_URL,
        api_key="test-key",
    )
    # Use a dummy mongo client with a very short timeout for the pipeline
    # (vector search will fail gracefully and fall back to keyword search,
    # which also returns empty — the LLM stub still produces the diagnoses)
    mongo_client = AsyncIOMotorClient(
        "mongodb://localhost:27017",
        serverSelectionTimeoutMS=100,  # fail fast
        connectTimeoutMS=100,
    )
    database = mongo_client["diagno_pilot_test"]
    index_manager = IndexManager(db=database)
    pipeline = LlamaIndexPipeline(
        index_manager=index_manager,
        llm_router=llm_router,
        embedder=embedder,
    )
    integration_app.state.diagnostic_service = DiagnosticService(rag_service=pipeline)


def _mock_llm_endpoints(router=None):
    """Register respx stubs for both the embedding and chat/completions endpoints."""
    r = router or respx.mock
    r.post(f"{_LLM_BASE_URL}/embeddings").mock(
        return_value=httpx.Response(200, json=_STUB_EMBEDDING_RESPONSE)
    )
    r.post(f"{_LLM_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json=_STUB_CHAT_RESPONSE)
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_SYMPTOMS = [
    {"name": "fièvre", "severity": "high", "duration_days": 3},
    {"name": "céphalées", "severity": "moderate", "duration_days": 2},
    {"name": "frissons", "severity": "moderate", "duration_days": 3},
]

_ADULT_PATIENT = {
    "full_name": "Kofi Mensah",
    "weight_kg": 70.0,
    "age_group": "adult",
    "allergies": [],
    "comorbidities": {"renal_failure": False, "hepatic_failure": False},
    "current_medications": [],
}

# Patient allergic to ciprofloxacin — ciprofloxacin protocol has alternative="ceftriaxone"
# so the allergy alert will have a non-null alternative (Requirement 4.2).
_CIPROFLOXACIN_ALLERGY_PATIENT = {
    "full_name": "Ama Owusu",
    "weight_kg": 65.0,
    "age_group": "adult",
    "allergies": ["ciprofloxacin"],
    "comorbidities": {"renal_failure": False, "hepatic_failure": False},
    "current_medications": [],
}

_CHILD_PATIENT = {
    "full_name": "Kwame Junior",
    "weight_kg": 20.0,
    "age_group": "child",
    "allergies": [],
    "comorbidities": {"renal_failure": False, "hepatic_failure": False},
    "current_medications": [],
}

_RENAL_FAILURE_PATIENT = {
    "full_name": "Abena Asante",
    "weight_kg": 68.0,
    "age_group": "adult",
    "allergies": [],
    "comorbidities": {"renal_failure": True, "hepatic_failure": False},
    "current_medications": [],
}


# ---------------------------------------------------------------------------
# Test 1 — Symptom submission returns ≥ 3 diagnoses with valid structure
# Validates: Requirement 4.1
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_symptom_submission_returns_diagnoses(integration_app, medecin_client: AsyncClient):
    _setup_diagnostic_service(integration_app)

    with respx.mock(assert_all_mocked=True) as mock_router:
        _mock_llm_endpoints(mock_router)
        resp = await medecin_client.post(
            "/api/v1/diagnose/symptoms",
            json={"symptoms": _DEFAULT_SYMPTOMS},
        )
    assert resp.status_code == 200, f"diagnose failed: {resp.text}"
    body = resp.json()

    assert "session_id" in body
    assert "diagnoses" in body
    diagnoses = body["diagnoses"]

    assert len(diagnoses) >= 3, f"Expected ≥ 3 diagnoses, got {len(diagnoses)}"
    for d in diagnoses:
        assert 0.0 <= d["probability"] <= 1.0, (
            f"probability {d['probability']} out of [0.0, 1.0]"
        )
        assert d.get("icd_code"), f"icd_code must be non-empty, got {d.get('icd_code')!r}"


# ---------------------------------------------------------------------------
# Test 2 — Prescription for patient with known allergy returns critical allergy alert
# with non-null alternative
# Validates: Requirement 4.2
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_prescription_allergy_alert(medecin_client: AsyncClient):
    """Patient allergic to ciprofloxacin prescribed ciprofloxacin → critical allergy alert with non-null alternative."""
    resp = await medecin_client.post(
        "/api/v1/diagnose/prescription",
        json={
            "antibiotic": "ciprofloxacin",
            "patient_profile": _CIPROFLOXACIN_ALLERGY_PATIENT,
        },
    )
    assert resp.status_code == 200, f"prescription failed: {resp.text}"
    body = resp.json()

    alerts = body.get("alerts", [])
    allergy_alerts = [
        a for a in alerts
        if a.get("level") == "critical" and a.get("type") == "allergy"
    ]
    assert allergy_alerts, (
        f"Expected at least one critical allergy alert, got alerts: {alerts}"
    )
    assert allergy_alerts[0]["level"] == "critical"
    assert allergy_alerts[0]["type"] == "allergy"
    # ciprofloxacin protocol has alternative="ceftriaxone"
    assert allergy_alerts[0].get("alternative") is not None, (
        f"Expected non-null alternative in allergy alert, got: {allergy_alerts[0]}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Fluoroquinolone for child patient returns critical contraindication alert
# Validates: Requirement 4.3
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_fluoroquinolone_child_contraindication(medecin_client: AsyncClient):
    """Ciprofloxacin (fluoroquinolone) for a child → critical contraindication alert."""
    resp = await medecin_client.post(
        "/api/v1/diagnose/prescription",
        json={
            "antibiotic": "ciprofloxacin",
            "patient_profile": _CHILD_PATIENT,
        },
    )
    assert resp.status_code == 200, f"prescription failed: {resp.text}"
    body = resp.json()

    alerts = body.get("alerts", [])
    contraindication_alerts = [
        a for a in alerts
        if a.get("level") == "critical" and a.get("type") == "contraindication"
    ]
    assert contraindication_alerts, (
        f"Expected at least one critical contraindication alert for ciprofloxacin + child, "
        f"got alerts: {alerts}"
    )


# ---------------------------------------------------------------------------
# Test 4 — Prescription for renal failure patient has reduced dose_mg
# Validates: Requirement 4.4
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_renal_failure_reduces_dose(medecin_client: AsyncClient):
    """Renal failure patient → dose_mg reduced relative to standard adult dose."""
    # Standard adult dose (no renal failure)
    resp_normal = await medecin_client.post(
        "/api/v1/diagnose/prescription",
        json={
            "antibiotic": "amoxicillin",
            "patient_profile": _ADULT_PATIENT,
        },
    )
    assert resp_normal.status_code == 200
    normal_dose = resp_normal.json()["prescription"]["dose_mg"]

    # Renal failure patient
    resp_renal = await medecin_client.post(
        "/api/v1/diagnose/prescription",
        json={
            "antibiotic": "amoxicillin",
            "patient_profile": _RENAL_FAILURE_PATIENT,
        },
    )
    assert resp_renal.status_code == 200
    renal_dose = resp_renal.json()["prescription"]["dose_mg"]

    assert renal_dose < normal_dose, (
        f"Expected reduced dose for renal failure patient: "
        f"renal={renal_dose}, normal={normal_dose}"
    )


# ---------------------------------------------------------------------------
# Test 5 — Diagnose session round-trip: GET session returns same diagnoses
# Validates: Requirement 4.5
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_diagnose_session_round_trip(integration_app, medecin_client: AsyncClient):
    """GET /api/v1/diagnose/session/{session_id} returns same diagnoses as POST."""
    _setup_diagnostic_service(integration_app)

    with respx.mock(assert_all_mocked=True) as mock_router:
        _mock_llm_endpoints(mock_router)
        post_resp = await medecin_client.post(
            "/api/v1/diagnose/symptoms",
            json={"symptoms": _DEFAULT_SYMPTOMS},
        )
    assert post_resp.status_code == 200, f"diagnose POST failed: {post_resp.text}"
    post_body = post_resp.json()
    session_id = post_body["session_id"]
    original_diagnoses = post_body["diagnoses"]

    get_resp = await medecin_client.get(f"/api/v1/diagnose/session/{session_id}")
    assert get_resp.status_code == 200, f"session GET failed: {get_resp.text}"
    session_body = get_resp.json()
    session_diagnoses = session_body["diagnoses"]

    assert len(session_diagnoses) == len(original_diagnoses), (
        f"Session diagnoses count mismatch: "
        f"original={len(original_diagnoses)}, session={len(session_diagnoses)}"
    )
    for orig, sess in zip(original_diagnoses, session_diagnoses):
        assert orig["condition"] == sess["condition"]
        assert abs(orig["probability"] - sess["probability"]) < 1e-6
        assert orig.get("icd_code") == sess.get("icd_code")


# ---------------------------------------------------------------------------
# Strategies for property tests
# ---------------------------------------------------------------------------

_symptom_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Zs")),
    min_size=1,
    max_size=30,
).map(str.strip).filter(lambda s: len(s) >= 1)

_symptom_strategy = st.fixed_dictionaries({
    "name": _symptom_name_strategy,
    "severity": st.sampled_from(["low", "moderate", "high"]),
    "duration_days": st.integers(min_value=1, max_value=30),
})

_symptoms_list_strategy = st.lists(_symptom_strategy, min_size=1, max_size=5)


# ---------------------------------------------------------------------------
# Subtask 5.1 — Property 5: Diagnose response structure
# Feature: testing-coverage, Property 5: Diagnose response structure
# Validates: Requirements 4.1
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@given(symptoms=_symptoms_list_strategy)
@settings(max_examples=5, deadline=None)
async def test_property_diagnose_response_structure(integration_app, symptoms: list[dict]):
    """
    Property 5: Diagnose response structure
    For any non-empty symptom list (LLM stubbed), response SHALL contain ≥ 3
    diagnoses each with probability in [0.0, 1.0] and non-empty icd_code.

    # Feature: testing-coverage, Property 5: Diagnose response structure
    Validates: Requirements 4.1
    """
    _setup_diagnostic_service(integration_app)

    # Reset rate limiter for each Hypothesis example
    from backend.core.rate_limit import limiter
    try:
        limiter._storage.reset()
    except Exception:
        pass

    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        login_resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "medecin@test.local", "password": "TestPassword123!"},
        )
        assert login_resp.status_code == 200

        with respx.mock(assert_all_mocked=True) as mock_router:
            _mock_llm_endpoints(mock_router)
            resp = await client.post(
                "/api/v1/diagnose/symptoms",
                json={"symptoms": symptoms},
            )
        assert resp.status_code == 200, f"diagnose failed: {resp.text}"
        body = resp.json()

        diagnoses = body.get("diagnoses", [])
        assert len(diagnoses) >= 3, (
            f"Expected ≥ 3 diagnoses for symptoms={symptoms}, got {len(diagnoses)}"
        )
        for d in diagnoses:
            assert 0.0 <= d["probability"] <= 1.0, (
                f"probability {d['probability']} out of [0.0, 1.0]"
            )
            assert d.get("icd_code"), (
                f"icd_code must be non-empty, got {d.get('icd_code')!r}"
            )


# ---------------------------------------------------------------------------
# Subtask 5.2 — Property 6: Diagnose session round-trip
# Feature: testing-coverage, Property 6: Diagnose session round-trip
# Validates: Requirements 4.5
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@given(symptoms=_symptoms_list_strategy)
@settings(max_examples=5, deadline=None)
async def test_property_diagnose_session_round_trip(integration_app, symptoms: list[dict]):
    """
    Property 6: Diagnose session round-trip
    For any diagnose session, GET session SHALL return diagnoses equivalent to
    the original POST response.

    # Feature: testing-coverage, Property 6: Diagnose session round-trip
    Validates: Requirements 4.5
    """
    _setup_diagnostic_service(integration_app)

    # Reset rate limiter for each Hypothesis example
    from backend.core.rate_limit import limiter
    try:
        limiter._storage.reset()
    except Exception:
        pass

    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        login_resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "medecin@test.local", "password": "TestPassword123!"},
        )
        assert login_resp.status_code == 200

        with respx.mock(assert_all_mocked=True) as mock_router:
            _mock_llm_endpoints(mock_router)
            post_resp = await client.post(
                "/api/v1/diagnose/symptoms",
                json={"symptoms": symptoms},
            )
        assert post_resp.status_code == 200, f"diagnose POST failed: {post_resp.text}"
        post_body = post_resp.json()
        session_id = post_body["session_id"]
        original_diagnoses = post_body["diagnoses"]

        get_resp = await client.get(f"/api/v1/diagnose/session/{session_id}")
        assert get_resp.status_code == 200, f"session GET failed: {get_resp.text}"
        session_diagnoses = get_resp.json()["diagnoses"]

        assert len(session_diagnoses) == len(original_diagnoses), (
            f"Diagnoses count mismatch: "
            f"original={len(original_diagnoses)}, session={len(session_diagnoses)}"
        )
        for orig, sess in zip(original_diagnoses, session_diagnoses):
            assert orig["condition"] == sess["condition"]
            assert abs(orig["probability"] - sess["probability"]) < 1e-6
            assert orig.get("icd_code") == sess.get("icd_code")
