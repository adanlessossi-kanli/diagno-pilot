"""
Smoke tests for legacy non-streaming code removal and backward compatibility.

Feature: llm-response-streaming, Task 10.4

Verifies:
  - ChatMessageResponse, sendMessage, ChatService.send_message no longer exist
  - LLMRouter.generate() and LlamaIndexPipeline.query() still work for diagnose pipeline
  - POST /api/v1/chat/message returns text/event-stream

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.services.chat_service import ChatService
from backend.services.llamaindex_pipeline import StreamEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_SKIP_DIRS = {"__pycache__", ".git", ".hypothesis", "node_modules", ".kiro"}


def _python_source_files() -> list[Path]:
    """Collect all .py files under the backend/ tree (excluding tests)."""
    result: list[Path] = []
    for dirpath, dirnames, filenames in __import__("os").walk(_BACKEND_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                result.append(Path(dirpath) / fname)
    return result


# ---------------------------------------------------------------------------
# 1. ChatMessageResponse no longer exists in backend/routers/chat.py
# ---------------------------------------------------------------------------

def test_chat_message_response_removed():
    """ChatMessageResponse Pydantic model must not exist in chat router.

    Requirements: 9.1, 9.2
    """
    from backend.routers import chat as chat_module
    assert not hasattr(chat_module, "ChatMessageResponse"), (
        "ChatMessageResponse should have been removed from backend/routers/chat.py"
    )


# ---------------------------------------------------------------------------
# 2. ChatService.send_message no longer exists
# ---------------------------------------------------------------------------

def test_chat_service_send_message_removed():
    """ChatService must not have a send_message method (only send_message_stream).

    Requirements: 9.4
    """
    assert not hasattr(ChatService, "send_message"), (
        "ChatService.send_message should have been removed; "
        "only send_message_stream should remain"
    )
    # Verify send_message_stream exists
    assert hasattr(ChatService, "send_message_stream"), (
        "ChatService.send_message_stream must exist as the replacement"
    )


# ---------------------------------------------------------------------------
# 3. sendMessage no longer exists in packages/api-client/index.ts
# ---------------------------------------------------------------------------

def test_send_message_removed_from_api_client():
    """The sendMessage method must not exist in the API client source.

    Requirements: 9.3
    """
    api_client_path = _BACKEND_ROOT.parent / "packages" / "api-client" / "index.ts"
    if not api_client_path.exists():
        pytest.skip("API client source not found")

    content = api_client_path.read_text(encoding="utf-8")
    # Filter out sendMessageStream matches
    non_stream_matches = [
        m for m in re.finditer(r"\bsendMessage\b(?!Stream)", content)
    ]
    assert len(non_stream_matches) == 0, (
        f"Found {len(non_stream_matches)} reference(s) to sendMessage "
        f"(non-streaming) in packages/api-client/index.ts — it should be removed"
    )


# ---------------------------------------------------------------------------
# 4. LLMRouter.generate() still works for diagnose pipeline
# ---------------------------------------------------------------------------

def test_llm_router_generate_still_exists():
    """LLMRouter.generate() must be preserved for non-chat callers.

    Requirements: 9.5
    """
    from backend.services.llm_router import LLMRouter
    assert hasattr(LLMRouter, "generate"), (
        "LLMRouter.generate() must be preserved for the diagnose pipeline"
    )
    assert inspect.iscoroutinefunction(LLMRouter.generate), (
        "LLMRouter.generate must be an async method"
    )


# ---------------------------------------------------------------------------
# 5. LlamaIndexPipeline.query() still works for diagnose pipeline
# ---------------------------------------------------------------------------

def test_llamaindex_pipeline_query_still_exists():
    """LlamaIndexPipeline.query() must be preserved for non-chat callers.

    Requirements: 9.5
    """
    from backend.services.llamaindex_pipeline import LlamaIndexPipeline
    assert hasattr(LlamaIndexPipeline, "query"), (
        "LlamaIndexPipeline.query() must be preserved for the diagnose pipeline"
    )
    assert inspect.iscoroutinefunction(LlamaIndexPipeline.query), (
        "LlamaIndexPipeline.query must be an async method"
    )


# ---------------------------------------------------------------------------
# 6. POST /api/v1/chat/message returns text/event-stream
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_endpoint_returns_event_stream():
    """POST /api/v1/chat/message must return Content-Type: text/event-stream.

    Requirements: 9.1
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.auth import get_current_user
    from backend.routers.chat import get_chat_service
    from bson import ObjectId
    from datetime import datetime, timezone

    user = {
        "_id": ObjectId(),
        "email": "test@test.com",
        "role": "medecin",
        "full_name": "Test User",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }

    mock_svc = MagicMock()

    async def _fake_stream(*args, **kwargs):
        yield StreamEvent(type="token", content="Hello")
        yield StreamEvent(type="done", answer="Hello", sources=[], llm_used="mock")

    mock_svc.send_message_stream = MagicMock(side_effect=_fake_stream)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_chat_service] = lambda: mock_svc

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/chat/message",
                json={"message": "Hello", "session_id": None},
                headers={"Authorization": "Bearer fake"},
            )
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type, (
            f"Expected text/event-stream, got {content_type}"
        )
    finally:
        app.dependency_overrides.clear()
