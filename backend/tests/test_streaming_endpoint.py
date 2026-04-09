"""Unit tests for the streaming chat endpoint POST /api/v1/chat/message.

Tests:
- Auth enforcement (401)
- Rate limiting (429)
- Request validation (422)
- Full SSE stream integration with mocked ChatService

Validates: Requirements 4.1, 4.5, 4.6
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from bson import ObjectId
from fastapi import FastAPI, HTTPException

from backend.core.auth import get_current_user
from backend.models.document import DocumentSource
from backend.routers.chat import router, get_chat_service
from backend.services.llamaindex_pipeline import StreamEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    """Reset sse-starlette's AppStatus event so it binds to the current loop."""
    import asyncio as _asyncio
    from sse_starlette.sse import AppStatus
    AppStatus.should_exit_event = _asyncio.Event()
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_USER = {
    "_id": ObjectId(),
    "email": "test@example.com",
    "role": "medecin",
    "full_name": "Dr. Test",
}

_VALID_BODY = {"message": "Hello doctor"}


def _create_test_app(chat_service_mock=None, auth_user=None, auth_raises_401=False):
    """Build a minimal FastAPI app with the chat router for testing.

    Includes SlowAPI middleware with the global limiter so the
    ``@limiter.limit`` decorator on the real router works correctly.
    """
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from starlette.responses import JSONResponse
    from backend.core.rate_limit import limiter

    app = FastAPI()
    app.state.limiter = limiter

    app.add_exception_handler(
        RateLimitExceeded,
        lambda req, exc: JSONResponse(
            {"error": f"Rate limit exceeded: {exc.detail}"}, status_code=429,
        ),
    )

    # Pre-initialise view_rate_limit on request.state (mirrors main.py middleware)
    @app.middleware("http")
    async def _init_rate_limit_state(request, call_next):
        if not hasattr(request.state, "view_rate_limit"):
            request.state.view_rate_limit = None
        return await call_next(request)

    app.add_middleware(SlowAPIMiddleware)

    if chat_service_mock is not None:
        app.dependency_overrides[get_chat_service] = lambda: chat_service_mock
    else:
        app.dependency_overrides[get_chat_service] = lambda: MagicMock()

    if auth_raises_401:
        async def _raise_401():
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        app.dependency_overrides[get_current_user] = _raise_401
    elif auth_user is not None:
        app.dependency_overrides[get_current_user] = lambda: auth_user

    app.include_router(router, prefix="/api/v1")
    return app


def _parse_sse(body: str) -> list[dict]:
    """Parse raw SSE text into a list of {event, data} dicts."""
    events = []
    current_event = None
    current_data = None

    for line in body.splitlines():
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_data = line[len("data:"):].strip()
        elif line == "" and current_event is not None and current_data is not None:
            events.append({"event": current_event, "data": current_data})
            current_event = None
            current_data = None

    # Handle trailing event without final blank line
    if current_event is not None and current_data is not None:
        events.append({"event": current_event, "data": current_data})

    return events


# ---------------------------------------------------------------------------
# Test: Auth enforcement (401)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401():
    """Unauthenticated requests to the streaming endpoint get HTTP 401.

    Validates: Requirement 4.6
    """
    app = _create_test_app(auth_raises_401=True)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/chat/message", json=_VALID_BODY)

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test: Rate limiting (429)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_returns_429_after_60_requests():
    """Exceeding 60 requests/minute on the streaming endpoint returns 429.

    Patches the global limiter's storage to use in-memory backend so
    rate limiting is enforced without Redis.

    Validates: Requirement 4.6
    """
    from backend.core.rate_limit import limiter
    from limits.storage import MemoryStorage

    # Swap the limiter's storage to in-memory for this test
    original_storage = limiter._storage
    mem_storage = MemoryStorage()
    limiter._storage = mem_storage
    # Also swap on the inner limiter object
    original_inner_storage = limiter.limiter.storage
    limiter.limiter.storage = mem_storage

    mock_chat_service = MagicMock()

    async def _fake_stream(**kwargs):
        yield StreamEvent(type="token", content="ok")
        yield StreamEvent(type="done", answer="ok", sources=[], llm_used="m")

    mock_chat_service.send_message_stream = _fake_stream

    app = _create_test_app(chat_service_mock=mock_chat_service, auth_user=_VALID_USER)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Send 60 requests — all should succeed
            for i in range(60):
                resp = await client.post("/api/v1/chat/message", json=_VALID_BODY)
                assert resp.status_code != 429, (
                    f"Request {i+1} was rate-limited prematurely"
                )

            # The 61st request must be 429
            resp = await client.post("/api/v1/chat/message", json=_VALID_BODY)
            assert resp.status_code == 429
    finally:
        # Restore original storage
        limiter._storage = original_storage
        limiter.limiter.storage = original_inner_storage


# ---------------------------------------------------------------------------
# Test: Request validation (422)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_message_returns_422():
    """An empty message body should fail validation with 422.

    Validates: Requirement 4.1
    """
    app = _create_test_app(auth_user=_VALID_USER)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/chat/message", json={"message": ""})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_message_too_long_returns_422():
    """A message exceeding 4000 characters should fail validation with 422.

    Validates: Requirement 4.1
    """
    app = _create_test_app(auth_user=_VALID_USER)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/chat/message", json={"message": "x" * 4001}
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test: Full SSE stream integration with mocked ChatService
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sse_stream_token_done_events():
    """The endpoint streams token and done SSE events from ChatService.

    Validates: Requirements 4.3, 4.4, 4.5
    """
    source = DocumentSource(
        document_id="doc1", title="Guide", source="OMS",
        section=None, excerpt=None, page=None,
    )
    events = [
        StreamEvent(type="token", content="Hello"),
        StreamEvent(type="token", content=" world"),
        StreamEvent(
            type="done", answer="Hello world", sources=[source],
            llm_used="MedicalQwen3-Reasoning-4B", fallback_used=False,
        ),
    ]

    mock_chat_service = MagicMock()

    async def _fake_stream(**kwargs):
        for e in events:
            yield e

    mock_chat_service.send_message_stream = _fake_stream

    app = _create_test_app(chat_service_mock=mock_chat_service, auth_user=_VALID_USER)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/chat/message", json=_VALID_BODY)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    # Parse SSE events from the response body
    sse_events = _parse_sse(resp.text)

    # Expect 2 token events + 1 done event
    token_events = [e for e in sse_events if e["event"] == "token"]
    done_events = [e for e in sse_events if e["event"] == "done"]

    assert len(token_events) == 2
    assert json.loads(token_events[0]["data"])["content"] == "Hello"
    assert json.loads(token_events[1]["data"])["content"] == " world"

    assert len(done_events) == 1
    done_data = json.loads(done_events[0]["data"])
    assert done_data["answer"] == "Hello world"
    assert done_data["llm_used"] == "MedicalQwen3-Reasoning-4B"
    assert done_data["fallback_warning"] is None
    assert done_data["warnings_present"] is False
    assert isinstance(done_data["sources"], list)
    assert len(done_data["sources"]) == 1


@pytest.mark.asyncio
async def test_sse_stream_error_event():
    """The endpoint streams an error SSE event when ChatService yields an error.

    Validates: Requirement 4.5
    """
    events = [
        StreamEvent(type="token", content="partial"),
        StreamEvent(type="error", error="LLM unavailable", retryable=True),
    ]

    mock_chat_service = MagicMock()

    async def _fake_stream(**kwargs):
        for e in events:
            yield e

    mock_chat_service.send_message_stream = _fake_stream

    app = _create_test_app(chat_service_mock=mock_chat_service, auth_user=_VALID_USER)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/chat/message", json=_VALID_BODY)

    assert resp.status_code == 200

    sse_events = _parse_sse(resp.text)
    error_events = [e for e in sse_events if e["event"] == "error"]

    assert len(error_events) == 1
    error_data = json.loads(error_events[0]["data"])
    assert error_data["error"] == "LLM unavailable"
    assert error_data["retryable"] is True
