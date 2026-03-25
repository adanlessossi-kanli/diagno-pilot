# Feature: diagno-pilot-improvements, Property 3: Rate limiter retourne 429 avec Retry-After au dépassement
"""
Tests de propriété pour le rate limiting — Diagno-Pilot

Property 3 : Rate limiter retourne 429 avec Retry-After au dépassement
**Validates: Requirements 2.1, 2.2, 2.3**

Pour tout utilisateur authentifié qui émet plus de N requêtes par minute sur
un endpoint limité (N = 30 pour /diagnose/symptoms, N = 60 pour /chat/message),
la réponse à la (N+1)ème requête doit avoir le statut HTTP 429 et contenir
l'en-tête Retry-After.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.routers.auth import create_access_token

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate realistic user IDs (MongoDB ObjectId hex strings)
user_id_strategy = st.builds(lambda: str(ObjectId()))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIAGNOSE_LIMIT = 30
CHAT_LIMIT = 60


def _make_user_doc(user_id: str) -> dict:
    """Build a minimal user document for mocking get_current_user."""
    return {
        "_id": ObjectId(user_id),
        "email": f"{user_id[:8]}@test.com",
        "role": "medecin",
        "full_name": "Dr. Test",
        "locale": "fr",
    }


def _make_token(user_id: str) -> str:
    return create_access_token(user_id=user_id, role="medecin")


def _reset_rate_limiter():
    """Clear the in-memory rate limiter storage."""
    from backend.core.rate_limit import limiter
    try:
        storage = limiter._storage
        if hasattr(storage, "_storage"):
            storage._storage.clear()
        elif hasattr(storage, "storage"):
            storage.storage.clear()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Property 3a — POST /diagnose/symptoms → 429 après 30 requêtes
# ---------------------------------------------------------------------------

@given(user_id=user_id_strategy)
@h_settings(max_examples=10, deadline=None)
def test_p3a_diagnose_symptoms_rate_limit_429(user_id: str):
    """
    Feature: diagno-pilot-improvements, Property 3:
    Pour tout utilisateur authentifié, après 30 requêtes sur POST /diagnose/symptoms,
    la (31ème) requête doit retourner HTTP 429 avec l'en-tête Retry-After.

    **Validates: Requirements 2.1, 2.3**
    """
    _reset_rate_limiter()

    async def _run():
        from httpx import AsyncClient, ASGITransport
        from backend.main import app
        from backend.core.auth import get_current_user
        from backend.routers.diagnose import get_diagnostic_service

        user_doc = _make_user_doc(user_id)
        token = _make_token(user_id)

        # Mock get_current_user to avoid DB lookup
        async def mock_get_current_user():
            return user_doc

        # Mock DiagnosticService to avoid LLM/DB calls
        mock_diag_service = MagicMock()
        mock_diag_service.get_differential_diagnosis = AsyncMock(return_value=[])

        # Mock DB insert for consultations
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        app.dependency_overrides[get_current_user] = mock_get_current_user
        app.dependency_overrides[get_diagnostic_service] = lambda: mock_diag_service

        try:
            with patch("backend.routers.diagnose.db") as mock_db_obj:
                mock_db_obj.get_db.return_value = mock_db

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    headers = {"Authorization": f"Bearer {token}"}
                    body = {"symptoms": [{"name": "fever", "severity": "mild", "duration_days": 1}]}

                    # Send exactly DIAGNOSE_LIMIT requests — all should succeed (or at least not 429)
                    for i in range(DIAGNOSE_LIMIT):
                        resp = await client.post(
                            "/api/v1/diagnose/symptoms", json=body, headers=headers
                        )
                        assert resp.status_code != 429, (
                            f"Request {i+1} was rate-limited prematurely (expected limit={DIAGNOSE_LIMIT})"
                        )

                    # The (N+1)th request must be 429
                    resp = await client.post(
                        "/api/v1/diagnose/symptoms", json=body, headers=headers
                    )
                    assert resp.status_code == 429, (
                        f"Expected 429 on request {DIAGNOSE_LIMIT+1}, got {resp.status_code}"
                    )
                    assert "retry-after" in resp.headers, (
                        f"Expected Retry-After header in 429 response, got headers: {dict(resp.headers)}"
                    )
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_diagnostic_service, None)
            _reset_rate_limiter()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Property 3b — POST /chat/message → 429 après 60 requêtes
# ---------------------------------------------------------------------------

@given(user_id=user_id_strategy)
@h_settings(max_examples=10, deadline=None)
def test_p3b_chat_message_rate_limit_429(user_id: str):
    """
    Feature: diagno-pilot-improvements, Property 3:
    Pour tout utilisateur authentifié, après 60 requêtes sur POST /chat/message,
    la (61ème) requête doit retourner HTTP 429 avec l'en-tête Retry-After.

    **Validates: Requirements 2.2, 2.3**
    """
    _reset_rate_limiter()

    async def _run():
        from httpx import AsyncClient, ASGITransport
        from backend.main import app
        from backend.core.auth import get_current_user
        from backend.routers.chat import get_chat_service

        user_doc = _make_user_doc(user_id)
        token = _make_token(user_id)

        # Mock get_current_user to avoid DB lookup
        async def mock_get_current_user():
            return user_doc

        # Mock ChatService to avoid LLM/DB calls
        mock_chat_service = MagicMock()
        from backend.models.document import RAGResponse
        mock_rag_response = RAGResponse(answer="ok", sources=[], llm_used="mock")
        mock_chat_service.send_message = AsyncMock(return_value=("session-123", mock_rag_response))

        app.dependency_overrides[get_current_user] = mock_get_current_user
        app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                headers = {"Authorization": f"Bearer {token}"}
                body = {"message": "test message"}

                # Send exactly CHAT_LIMIT requests — all should succeed (or at least not 429)
                for i in range(CHAT_LIMIT):
                    resp = await client.post(
                        "/api/v1/chat/message", json=body, headers=headers
                    )
                    assert resp.status_code != 429, (
                        f"Request {i+1} was rate-limited prematurely (expected limit={CHAT_LIMIT})"
                    )

                # The (N+1)th request must be 429
                resp = await client.post(
                    "/api/v1/chat/message", json=body, headers=headers
                )
                assert resp.status_code == 429, (
                    f"Expected 429 on request {CHAT_LIMIT+1}, got {resp.status_code}"
                )
                assert "retry-after" in resp.headers, (
                    f"Expected Retry-After header in 429 response, got headers: {dict(resp.headers)}"
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_chat_service, None)
            _reset_rate_limiter()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Property 3c — Isolation entre utilisateurs différents
# ---------------------------------------------------------------------------

@given(
    user_id_a=user_id_strategy,
    user_id_b=user_id_strategy,
)
@h_settings(max_examples=10, deadline=None)
def test_p3c_rate_limit_isolation_between_users(user_id_a: str, user_id_b: str):
    """
    Feature: diagno-pilot-improvements, Property 3 (isolation):
    Les compteurs de rate limiting sont indépendants par utilisateur.
    Un utilisateur B ne doit pas être affecté par les requêtes de l'utilisateur A.

    **Validates: Requirements 2.1, 2.3**
    """
    # Skip if same user (trivially not isolated)
    if user_id_a == user_id_b:
        return

    _reset_rate_limiter()

    async def _run():
        from httpx import AsyncClient, ASGITransport
        from backend.main import app
        from backend.core.auth import get_current_user
        from backend.routers.diagnose import get_diagnostic_service

        user_doc_a = _make_user_doc(user_id_a)
        user_doc_b = _make_user_doc(user_id_b)
        token_a = _make_token(user_id_a)
        token_b = _make_token(user_id_b)

        # Track which user is "current" for the mock
        current_token_holder = {"token": token_a, "doc": user_doc_a}

        async def mock_get_current_user_dynamic():
            return current_token_holder["doc"]

        mock_diag_service = MagicMock()
        mock_diag_service.get_differential_diagnosis = AsyncMock(return_value=[])

        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        app.dependency_overrides[get_current_user] = mock_get_current_user_dynamic
        app.dependency_overrides[get_diagnostic_service] = lambda: mock_diag_service

        try:
            with patch("backend.routers.diagnose.db") as mock_db_obj:
                mock_db_obj.get_db.return_value = mock_db

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    body = {"symptoms": [{"name": "fever", "severity": "mild", "duration_days": 1}]}

                    # Exhaust user A's limit (send DIAGNOSE_LIMIT requests)
                    current_token_holder["doc"] = user_doc_a
                    for _ in range(DIAGNOSE_LIMIT):
                        await client.post(
                            "/api/v1/diagnose/symptoms",
                            json=body,
                            headers={"Authorization": f"Bearer {token_a}"},
                        )

                    # User A should now be rate-limited
                    current_token_holder["doc"] = user_doc_a
                    resp_a = await client.post(
                        "/api/v1/diagnose/symptoms",
                        json=body,
                        headers={"Authorization": f"Bearer {token_a}"},
                    )
                    assert resp_a.status_code == 429, (
                        f"User A should be rate-limited, got {resp_a.status_code}"
                    )

                    # User B should NOT be rate-limited (independent counter)
                    current_token_holder["doc"] = user_doc_b
                    resp_b = await client.post(
                        "/api/v1/diagnose/symptoms",
                        json=body,
                        headers={"Authorization": f"Bearer {token_b}"},
                    )
                    assert resp_b.status_code != 429, (
                        f"User B should NOT be rate-limited by User A's requests, got {resp_b.status_code}"
                    )
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_diagnostic_service, None)
            _reset_rate_limiter()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())
