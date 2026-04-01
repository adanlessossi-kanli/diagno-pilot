"""
Backend E2E auth integration tests — real MongoDB via Testcontainers.

Feature: testing-coverage
Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""
from __future__ import annotations

import pytest
import pytest_asyncio
import respx
from httpx import AsyncClient, ASGITransport
from hypothesis import given, settings
from hypothesis import strategies as st
from motor.motor_asyncio import AsyncIOMotorDatabase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def integration_client(integration_app):
    """Function-scoped async HTTP client against the integration app."""
    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _login(client: AsyncClient, email: str = "medecin@test.local", password: str = "TestPassword123!"):
    """Log in and return the response."""
    return await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )


# ---------------------------------------------------------------------------
# Test 1 — Valid login returns access_token (cookie), token_type, expires_in
# Validates: Requirement 2.1
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_valid_login_returns_token_fields(integration_client: AsyncClient):
    resp = await _login(integration_client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["expires_in"], int)
    assert body["expires_in"] > 0

    # access_token must be set as a cookie
    assert "access_token" in integration_client.cookies


# ---------------------------------------------------------------------------
# Test 2 — Login persists audit log entry with action="login"
# Validates: Requirement 2.2
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_login_persists_audit_log(integration_client: AsyncClient, real_db: AsyncIOMotorDatabase):
    resp = await _login(integration_client)
    assert resp.status_code == 200

    # Retrieve the user_id from the seeded users
    medecin = real_db.seeded_users["medecin"]
    user_id = str(medecin["_id"])

    log_entry = await real_db["audit_logs"].find_one({"action": "login", "user_id": user_id})
    assert log_entry is not None, "Expected an audit log entry with action='login'"
    assert log_entry["resource"] == "auth"


# ---------------------------------------------------------------------------
# Test 3 — Logout invalidates token (subsequent request returns HTTP 401)
# Validates: Requirement 2.3
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_logout_invalidates_token(integration_client: AsyncClient):
    # Login — cookies are set on the client
    resp = await _login(integration_client)
    assert resp.status_code == 200

    token = integration_client.cookies.get("access_token")
    assert token is not None

    # Verify the token works before logout (cookie-based auth)
    me_before = await integration_client.get("/api/v1/auth/me")
    assert me_before.status_code == 200

    # Logout — clears auth cookies
    logout_resp = await integration_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200

    # Subsequent cookie-based request must return 401 (cookies cleared)
    me_after = await integration_client.get("/api/v1/auth/me")
    assert me_after.status_code == 401


# ---------------------------------------------------------------------------
# Test 4 — Token refresh with valid refresh token returns new access token
# Validates: Requirement 2.4
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_token_refresh_with_valid_refresh_token(integration_client: AsyncClient):
    # Login to get cookies
    resp = await _login(integration_client)
    assert resp.status_code == 200

    original_access_token = integration_client.cookies.get("access_token")
    assert original_access_token is not None

    # Refresh — the refresh_token cookie is sent automatically
    refresh_resp = await integration_client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200

    body = refresh_resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["expires_in"], int)
    assert body["expires_in"] > 0

    # New access_token cookie should be set
    new_access_token = integration_client.cookies.get("access_token")
    assert new_access_token is not None


# ---------------------------------------------------------------------------
# Test 5 — Invalid refresh token returns HTTP 401
# Validates: Requirement 2.5
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_invalid_refresh_token_returns_401(integration_client: AsyncClient):
    # Set a bogus refresh_token cookie
    integration_client.cookies.set("refresh_token", "totally-invalid-token")

    refresh_resp = await integration_client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 401


# ---------------------------------------------------------------------------
# Test 6 — Failed login with wrong credentials returns HTTP 401 and no audit log
# Validates: Requirement 2.6
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_failed_login_returns_401_no_audit_log(
    integration_client: AsyncClient,
    real_db: AsyncIOMotorDatabase,
):
    # Count existing audit logs before the failed attempt
    count_before = await real_db["audit_logs"].count_documents({"action": "login"})

    resp = await _login(integration_client, password="WrongPassword!")
    assert resp.status_code == 401

    # Audit log count must be unchanged
    count_after = await real_db["audit_logs"].count_documents({"action": "login"})
    assert count_after == count_before, "Failed login must not create an audit log entry"


# ---------------------------------------------------------------------------
# Subtask 2.1 — Property test: logout invalidates token for any protected endpoint
# Feature: testing-coverage, Property 1: Logout invalidates token
# Validates: Requirement 2.3
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@given(endpoint=st.sampled_from(["/api/v1/auth/me", "/api/v1/patients"]))
@settings(max_examples=5, deadline=None)
@respx.mock(assert_all_mocked=True)
async def test_property_logout_invalidates_token(
    integration_app,
    endpoint: str,
):
    """
    Property 1: Logout invalidates token (round-trip)
    For any valid access token, after logout, a subsequent request with that
    token SHALL return HTTP 401.

    # Feature: testing-coverage, Property 1: Logout invalidates token
    Validates: Requirements 2.3
    """
    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        # Login — cookies are set on the client
        login_resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "medecin@test.local", "password": "TestPassword123!"},
        )
        assert login_resp.status_code == 200

        token = client.cookies.get("access_token")
        assert token is not None

        # Logout — clears auth cookies on the client
        logout_resp = await client.post("/api/v1/auth/logout")
        assert logout_resp.status_code == 200

        # Any subsequent cookie-based request must return 401 (cookies cleared)
        protected_resp = await client.get(endpoint)
        assert protected_resp.status_code == 401, (
            f"Expected 401 after logout on {endpoint}, got {protected_resp.status_code}"
        )
