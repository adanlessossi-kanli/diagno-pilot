# Feature: assistant-qa-and-documents-redesign, Property 10: Role-Based Access Control
"""
Property test for role-based access control on the Document Chat endpoint.

Property 10: Role-Based Access Control
For any user with a role in {admin, medecin, infirmière}, the
/api/v1/documents/chat endpoint SHALL return HTTP 200 (SSE stream).
For any user with a role NOT in that set, the endpoint SHALL return HTTP 403.

**Validates: Requirements 7.3, 11.3, 12.1, 12.2**
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest
from bson import ObjectId
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from fastapi import FastAPI

from backend.core.auth import get_current_user
from backend.routers.documents import router, get_doc_chat_service
from backend.services.llamaindex_pipeline import StreamEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    """Reset sse-starlette's AppStatus event so it binds to the current loop."""
    from sse_starlette.sse import AppStatus
    AppStatus.should_exit_event = asyncio.Event()
    yield


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_ROLES = {"admin", "medecin", "infirmière"}
ALL_ROLES = ["admin", "medecin", "infirmière", "pharmacien", "guest"]

_VALID_BODY = {"message": "What is the malaria protocol?"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role: str) -> dict:
    return {
        "_id": ObjectId(),
        "email": "test@example.com",
        "role": role,
        "full_name": "Test User",
    }


def _make_mock_doc_chat_service():
    """Return a mock DocumentChatService that yields a simple stream."""
    mock_svc = MagicMock()

    async def _fake_stream(**kwargs):
        yield StreamEvent(type="token", content="Answer")
        yield StreamEvent(
            type="done",
            answer="Answer",
            sources=[],
            llm_used="mock-llm",
            fallback_used=False,
        )

    mock_svc.send_message_stream = _fake_stream
    return mock_svc


def _create_test_app(auth_user=None):
    """Build a minimal FastAPI app with the documents router for RBAC testing."""
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from starlette.responses import JSONResponse
    from limits.storage import MemoryStorage
    from backend.core.rate_limit import limiter

    app = FastAPI()
    app.state.limiter = limiter

    # Use in-memory storage to avoid Redis dependency
    limiter._storage = MemoryStorage()
    limiter.limiter.storage = limiter._storage

    app.add_exception_handler(
        RateLimitExceeded,
        lambda req, exc: JSONResponse(
            {"error": f"Rate limit exceeded: {exc.detail}"}, status_code=429,
        ),
    )

    @app.middleware("http")
    async def _init_rate_limit_state(request, call_next):
        if not hasattr(request.state, "view_rate_limit"):
            request.state.view_rate_limit = None
        return await call_next(request)

    app.add_middleware(SlowAPIMiddleware)

    # Override DocumentChatService dependency
    mock_svc = _make_mock_doc_chat_service()
    app.dependency_overrides[get_doc_chat_service] = lambda: mock_svc

    # Override auth dependency
    if auth_user is not None:
        app.dependency_overrides[get_current_user] = lambda: auth_user

    app.include_router(router, prefix="/api/v1")
    return app


# ---------------------------------------------------------------------------
# Property 10: Role-Based Access Control
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(role=st.sampled_from(ALL_ROLES))
@pytest.mark.asyncio
async def test_property_10_role_based_access_control(role: str) -> None:
    """For any role, /api/v1/documents/chat returns 200 for allowed roles
    and 403 for others.

    **Validates: Requirements 7.3, 11.3, 12.1, 12.2**
    """
    user = _make_user(role)
    app = _create_test_app(auth_user=user)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/documents/chat", json=_VALID_BODY)

    if role in ALLOWED_ROLES:
        assert resp.status_code == 200, (
            f"Role '{role}' should be allowed (200), got {resp.status_code}"
        )
    else:
        assert resp.status_code == 403, (
            f"Role '{role}' should be denied (403), got {resp.status_code}"
        )
