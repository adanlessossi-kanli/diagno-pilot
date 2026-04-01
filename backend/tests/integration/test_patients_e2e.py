"""
Backend E2E patient CRUD integration tests — real MongoDB via Testcontainers.

Feature: testing-coverage
Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""
from __future__ import annotations

import pytest
import pytest_asyncio
import respx
import hypothesis
from httpx import AsyncClient, ASGITransport
from hypothesis import given, settings
from hypothesis import strategies as st
from motor.motor_asyncio import AsyncIOMotorDatabase


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Zs")),
    min_size=1,
    max_size=60,
).map(str.strip).filter(lambda s: len(s) >= 1)

_weight_strategy = st.floats(min_value=0.5, max_value=300.0, allow_nan=False, allow_infinity=False)

_allergy_strategy = st.lists(
    st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll")), min_size=1, max_size=20),
    max_size=5,
)

_medication_strategy = st.lists(
    st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll")), min_size=1, max_size=20),
    max_size=5,
)


def _patient_payload_strategy():
    return st.fixed_dictionaries({
        "full_name": _name_strategy,
        "weight_kg": _weight_strategy,
        "allergies": _allergy_strategy,
        "current_medications": _medication_strategy,
        "comorbidities": st.fixed_dictionaries({
            "renal_failure": st.booleans(),
            "hepatic_failure": st.booleans(),
        }),
    })


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


@pytest_asyncio.fixture
async def second_medecin_client(integration_app, real_db: AsyncIOMotorDatabase):
    """
    Async client authenticated as a second medecin user (created on-the-fly).
    Used for scope-isolation tests.
    """
    import bcrypt
    from datetime import datetime, timezone

    email = "medecin2@test.local"
    password = "TestPassword123!"

    # Insert a second medecin if not already present
    existing = await real_db["users"].find_one({"email": email})
    if existing is None:
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        await real_db["users"].insert_one({
            "email": email,
            "password_hash": password_hash,
            "full_name": "Dr. Amara Diallo",
            "role": "medecin",
            "locale": "fr",
            "created_at": datetime.now(timezone.utc),
            "last_login": None,
        })

    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )
        assert resp.status_code == 200, f"second medecin login failed: {resp.text}"
        yield client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_PATIENT = {
    "full_name": "Kwame Asante",
    "weight_kg": 72.5,
    "allergies": ["penicillin"],
    "current_medications": ["metformin"],
    "comorbidities": {"renal_failure": False, "hepatic_failure": False},
}


async def _create_patient(client: AsyncClient, payload: dict | None = None) -> dict:
    """POST /api/v1/patients and return the response body."""
    resp = await client.post("/api/v1/patients", json=payload or _DEFAULT_PATIENT)
    assert resp.status_code == 201, f"create_patient failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Test 1 — POST /api/v1/patients persists patient and returns _id
# Validates: Requirement 3.1
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_create_patient_returns_id(medecin_client: AsyncClient):
    body = await _create_patient(medecin_client)

    assert "id" in body, "Response must contain 'id'"
    assert body["id"] is not None
    assert body["full_name"] == _DEFAULT_PATIENT["full_name"]


# ---------------------------------------------------------------------------
# Test 2 — Create then fetch returns all submitted fields unchanged
# Validates: Requirement 3.2
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_create_then_fetch_returns_same_fields(medecin_client: AsyncClient):
    created = await _create_patient(medecin_client)
    patient_id = created["id"]

    resp = await medecin_client.get(f"/api/v1/patients/{patient_id}")
    assert resp.status_code == 200
    fetched = resp.json()

    assert fetched["full_name"] == _DEFAULT_PATIENT["full_name"]
    assert fetched["weight_kg"] == _DEFAULT_PATIENT["weight_kg"]
    assert fetched["allergies"] == _DEFAULT_PATIENT["allergies"]
    assert fetched["current_medications"] == _DEFAULT_PATIENT["current_medications"]
    assert fetched["comorbidities"] == _DEFAULT_PATIENT["comorbidities"]


# ---------------------------------------------------------------------------
# Test 3 — PUT /api/v1/patients/{id} updates are reflected in subsequent GET
# Validates: Requirement 3.3
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_update_patient_reflected_in_get(medecin_client: AsyncClient):
    created = await _create_patient(medecin_client)
    patient_id = created["id"]

    update_payload = {
        "full_name": "Kwame Asante Updated",
        "weight_kg": 80.0,
        "allergies": ["penicillin", "sulfa"],
        "current_medications": [],
        "comorbidities": {"renal_failure": True, "hepatic_failure": False},
    }

    put_resp = await medecin_client.put(f"/api/v1/patients/{patient_id}", json=update_payload)
    assert put_resp.status_code == 200

    get_resp = await medecin_client.get(f"/api/v1/patients/{patient_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.json()

    assert fetched["full_name"] == update_payload["full_name"]
    assert fetched["weight_kg"] == update_payload["weight_kg"]
    assert fetched["allergies"] == update_payload["allergies"]
    assert fetched["comorbidities"] == update_payload["comorbidities"]


# ---------------------------------------------------------------------------
# Test 4 — GET /api/v1/patients returns only the authenticated user's patients
# Validates: Requirement 3.4
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_patient_list_scoped_to_authenticated_user(
    medecin_client: AsyncClient,
    second_medecin_client: AsyncClient,
):
    # Create a patient as medecin1
    created = await _create_patient(medecin_client, {"full_name": "Patient Of Medecin1", "weight_kg": 60.0, "allergies": [], "current_medications": [], "comorbidities": {"renal_failure": False, "hepatic_failure": False}})
    medecin1_patient_id = created["id"]

    # Create a patient as medecin2
    await _create_patient(second_medecin_client, {"full_name": "Patient Of Medecin2", "weight_kg": 55.0, "allergies": [], "current_medications": [], "comorbidities": {"renal_failure": False, "hepatic_failure": False}})

    # medecin1's list must contain their own patient
    resp1 = await medecin_client.get("/api/v1/patients?page_size=100")
    assert resp1.status_code == 200
    ids1 = [p["id"] for p in resp1.json()["items"]]
    assert medecin1_patient_id in ids1

    # medecin1's list must NOT contain medecin2's patient names
    names1 = [p["full_name"] for p in resp1.json()["items"]]
    assert "Patient Of Medecin2" not in names1


# ---------------------------------------------------------------------------
# Test 5 — pharmacien user creating a patient returns HTTP 403
# Validates: Requirement 3.5
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_pharmacien_cannot_create_patient(integration_app, real_db: AsyncIOMotorDatabase):
    """
    pharmacien maps to 'guest' via LEGACY_ROLE_MAP and is not in the allowed
    roles for POST /api/v1/patients, so the endpoint must return HTTP 403.
    """
    import bcrypt
    from datetime import datetime, timezone

    email = "pharmacien@test.local"
    password = "TestPassword123!"

    existing = await real_db["users"].find_one({"email": email})
    if existing is None:
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        await real_db["users"].insert_one({
            "email": email,
            "password_hash": password_hash,
            "full_name": "Pharmacien Test",
            "role": "pharmacien",
            "locale": "fr",
            "created_at": datetime.now(timezone.utc),
            "last_login": None,
        })

    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        login_resp = await client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )
        assert login_resp.status_code == 200

        resp = await client.post("/api/v1/patients", json=_DEFAULT_PATIENT)
        assert resp.status_code == 403, (
            f"Expected 403 for pharmacien creating a patient, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Subtask 4.1 — Property 2: Patient create/fetch round-trip
# Feature: testing-coverage, Property 2: Patient create/fetch round-trip
# Validates: Requirements 3.2, 3.6
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@given(payload=_patient_payload_strategy())
@settings(max_examples=5, deadline=None)
async def test_property_patient_create_fetch_round_trip(integration_app, payload: dict):
    """
    Property 2: Patient create/fetch round-trip
    For any valid patient payload, create then fetch SHALL return all submitted
    fields equal to original values.

    # Feature: testing-coverage, Property 2: Patient create/fetch round-trip
    Validates: Requirements 3.2, 3.6
    """
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

        create_resp = await client.post("/api/v1/patients", json=payload)
        assert create_resp.status_code == 201, f"create failed: {create_resp.text}"
        created = create_resp.json()
        patient_id = created["id"]

        fetch_resp = await client.get(f"/api/v1/patients/{patient_id}")
        assert fetch_resp.status_code == 200
        fetched = fetch_resp.json()

        assert fetched["full_name"] == payload["full_name"]
        assert fetched["weight_kg"] == pytest.approx(payload["weight_kg"], rel=1e-5)
        assert fetched["allergies"] == payload["allergies"]
        assert fetched["current_medications"] == payload["current_medications"]
        assert fetched["comorbidities"]["renal_failure"] == payload["comorbidities"]["renal_failure"]
        assert fetched["comorbidities"]["hepatic_failure"] == payload["comorbidities"]["hepatic_failure"]


# ---------------------------------------------------------------------------
# Subtask 4.2 — Property 3: Patient list scope isolation
# Feature: testing-coverage, Property 3: Patient list scope isolation
# Validates: Requirement 3.4
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@given(
    name_a=_name_strategy,
    name_b=_name_strategy,
)
@settings(max_examples=5, deadline=None, suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture])
async def test_property_patient_list_scope_isolation(
    integration_app,
    real_db: AsyncIOMotorDatabase,
    name_a: str,
    name_b: str,
):
    """
    Property 3: Patient list scope isolation
    For any two distinct users, the patient list for user A SHALL NOT contain
    patients created by user B.

    # Feature: testing-coverage, Property 3: Patient list scope isolation
    Validates: Requirement 3.4
    """
    import bcrypt
    from datetime import datetime, timezone

    # Reset rate limiter for each Hypothesis example
    from backend.core.rate_limit import limiter
    try:
        limiter._storage.reset()
    except Exception:
        pass

    # Ensure a second medecin exists
    email_b = "medecin2@test.local"
    password = "TestPassword123!"
    if not await real_db["users"].find_one({"email": email_b}):
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        await real_db["users"].insert_one({
            "email": email_b,
            "password_hash": password_hash,
            "full_name": "Dr. Amara Diallo",
            "role": "medecin",
            "locale": "fr",
            "created_at": datetime.now(timezone.utc),
            "last_login": None,
        })

    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client_a, AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client_b:
        # Login both users
        resp_a = await client_a.post(
            "/api/v1/auth/login",
            data={"username": "medecin@test.local", "password": password},
        )
        assert resp_a.status_code == 200

        resp_b = await client_b.post(
            "/api/v1/auth/login",
            data={"username": email_b, "password": password},
        )
        assert resp_b.status_code == 200

        # Each user creates a uniquely-named patient
        payload_a = {**_DEFAULT_PATIENT, "full_name": f"PatientA_{name_a[:30]}"}
        payload_b = {**_DEFAULT_PATIENT, "full_name": f"PatientB_{name_b[:30]}"}

        create_a = await client_a.post("/api/v1/patients", json=payload_a)
        assert create_a.status_code == 201
        id_a = create_a.json()["id"]

        create_b = await client_b.post("/api/v1/patients", json=payload_b)
        assert create_b.status_code == 201
        id_b = create_b.json()["id"]

        # User A's list must contain their patient but NOT user B's
        list_a = await client_a.get("/api/v1/patients?page_size=100")
        assert list_a.status_code == 200
        ids_a = [p["id"] for p in list_a.json()["items"]]
        assert id_a in ids_a, "User A's patient must appear in their own list"
        assert id_b not in ids_a, "User B's patient must NOT appear in user A's list"

        # User B's list must contain their patient but NOT user A's
        list_b = await client_b.get("/api/v1/patients?page_size=100")
        assert list_b.status_code == 200
        ids_b = [p["id"] for p in list_b.json()["items"]]
        assert id_b in ids_b, "User B's patient must appear in their own list"
        assert id_a not in ids_b, "User A's patient must NOT appear in user B's list"


# ---------------------------------------------------------------------------
# Subtask 4.3 — Property 4: Patient update reflected in fetch (round-trip)
# Feature: testing-coverage, Property 4: Patient update reflected in fetch
# Validates: Requirement 3.3
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@given(update_payload=_patient_payload_strategy())
@settings(max_examples=5, deadline=None)
async def test_property_patient_update_round_trip(integration_app, update_payload: dict):
    """
    Property 4: Patient update reflected in fetch (round-trip)
    For any existing patient and valid update payload, update then fetch SHALL
    return updated field values.

    # Feature: testing-coverage, Property 4: Patient update reflected in fetch
    Validates: Requirement 3.3
    """
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

        # Create a baseline patient
        create_resp = await client.post("/api/v1/patients", json=_DEFAULT_PATIENT)
        assert create_resp.status_code == 201
        patient_id = create_resp.json()["id"]

        # Apply the generated update
        put_resp = await client.put(f"/api/v1/patients/{patient_id}", json=update_payload)
        assert put_resp.status_code == 200, f"update failed: {put_resp.text}"

        # Fetch and verify all updated fields match
        get_resp = await client.get(f"/api/v1/patients/{patient_id}")
        assert get_resp.status_code == 200
        fetched = get_resp.json()

        assert fetched["full_name"] == update_payload["full_name"]
        assert fetched["weight_kg"] == pytest.approx(update_payload["weight_kg"], rel=1e-5)
        assert fetched["allergies"] == update_payload["allergies"]
        assert fetched["current_medications"] == update_payload["current_medications"]
        assert fetched["comorbidities"]["renal_failure"] == update_payload["comorbidities"]["renal_failure"]
        assert fetched["comorbidities"]["hepatic_failure"] == update_payload["comorbidities"]["hepatic_failure"]
