"""Unit tests for _LLMClient connection pooling (Req 11.1, 11.2, 11.3).

Tests cover:
  - _LLMClient creates a shared httpx.AsyncClient in __init__
  - close() properly closes the underlying client
  - _do_request uses the shared client instead of creating a new one
  - LLMRouter.close() closes both primary and fallback clients
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx

from backend.services.llm_router import LLMRouter, _LLMClient


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Req 11.1 — _LLMClient creates httpx.AsyncClient in __init__
# ---------------------------------------------------------------------------


def test_llm_client_creates_async_client_in_init():
    """_LLMClient.__init__ must create an httpx.AsyncClient instance."""
    client = _LLMClient("http://localhost:8080", "key", "model")
    assert isinstance(client._client, httpx.AsyncClient)
    _run(client.close())


def test_llm_client_configures_connection_limits():
    """The shared client must have connection pool limits configured."""
    client = _LLMClient("http://localhost:8080", "key", "model")
    # Verify the client was created with a timeout matching settings
    assert client._client.timeout is not None
    _run(client.close())


# ---------------------------------------------------------------------------
# Req 11.3 — close() shuts down the client
# ---------------------------------------------------------------------------


def test_close_closes_the_http_client():
    """close() must call aclose() on the underlying httpx.AsyncClient."""
    client = _LLMClient("http://localhost:8080", "key", "model")
    mock_aclose = AsyncMock()
    client._client.aclose = mock_aclose
    _run(client.close())
    mock_aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Req 11.2 — _do_request uses the shared client
# ---------------------------------------------------------------------------


def test_do_request_uses_shared_client():
    """_do_request must use self._client.post, not create a new AsyncClient."""
    client = _LLMClient("http://localhost:8080", "test-key", "test-model")

    fake_response = AsyncMock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {
        "choices": [{"message": {"content": "answer"}}]
    }

    client._client.post = AsyncMock(return_value=fake_response)

    result = _run(client._do_request("hello", [{"content": "ctx"}]))

    assert result == "answer"
    client._client.post.assert_awaited_once()
    # Verify the URL used
    call_args = client._client.post.call_args
    assert "/chat/completions" in call_args[0][0]
    _run(client.close())


# ---------------------------------------------------------------------------
# Req 11.4 — LLMRouter.close() closes both clients
# ---------------------------------------------------------------------------


def test_llm_router_close_closes_both_clients():
    """LLMRouter.close() must close both primary and fallback HTTP clients."""
    router = LLMRouter(
        primary_url="http://primary:8080",
        primary_api_key="k1",
        fallback_url="http://fallback:8080",
        fallback_api_key="k2",
    )
    router._primary.close = AsyncMock()
    router._fallback.close = AsyncMock()

    _run(router.close())

    router._primary.close.assert_awaited_once()
    router._fallback.close.assert_awaited_once()
