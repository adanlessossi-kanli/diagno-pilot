"""Unit tests for _LLMClient.generate_stream().

Validates: Requirement 1.4 (error handling) and happy-path streaming.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest

from backend.core.retry import LLMUnavailableError
from backend.services.llm_router import _LLMClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeStreamResponse:
    """Mimics an httpx streaming response."""

    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            resp = httpx.Response(self.status_code, request=httpx.Request("POST", "http://fake"))
            raise httpx.HTTPStatusError("error", request=resp.request, response=resp)

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aclose(self) -> None:
        pass


def _make_stream_cm(lines: list[str], status_code: int = 200):
    resp = _FakeStreamResponse(lines, status_code)

    @asynccontextmanager
    async def _cm(*args, **kwargs):
        yield resp

    return _cm


def _token_line(content: str) -> str:
    return f'data: {json.dumps({"choices": [{"delta": {"content": content}}]})}'


def _done_line() -> str:
    return "data: [DONE]"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_happy_path_yields_tokens():
    """generate_stream yields token strings from a normal SSE response."""
    lines = [
        _token_line("Hello"),
        _token_line(" world"),
        _token_line("!"),
        _done_line(),
    ]
    client = _LLMClient("http://fake", "key", "model")

    async def run():
        with patch.object(client._client, "stream", side_effect=_make_stream_cm(lines)):
            return [tok async for tok in client.generate_stream("p", [{"content": "c"}], deadline=9999999)]

    tokens = asyncio.run(run())
    assert tokens == ["Hello", " world", "!"]


def test_connection_error_raises_llm_unavailable():
    """generate_stream raises LLMUnavailableError on connection failure."""
    client = _LLMClient("http://fake", "key", "model")

    @asynccontextmanager
    async def _raise_connect(*args, **kwargs):
        raise httpx.ConnectError("refused")
        yield  # pragma: no cover

    async def run():
        with patch.object(client._client, "stream", side_effect=_raise_connect):
            async for _ in client.generate_stream("p", [{"content": "c"}], deadline=9999999):
                pass  # pragma: no cover

    with pytest.raises(LLMUnavailableError, match="Streaming connection failed"):
        asyncio.run(run())


def test_timeout_raises_llm_unavailable():
    """generate_stream raises LLMUnavailableError on timeout."""
    client = _LLMClient("http://fake", "key", "model")

    @asynccontextmanager
    async def _raise_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")
        yield  # pragma: no cover

    async def run():
        with patch.object(client._client, "stream", side_effect=_raise_timeout):
            async for _ in client.generate_stream("p", [{"content": "c"}], deadline=9999999):
                pass  # pragma: no cover

    with pytest.raises(LLMUnavailableError, match="Streaming connection failed"):
        asyncio.run(run())


def test_http_error_raises_llm_unavailable():
    """generate_stream raises LLMUnavailableError on non-2xx status."""
    client = _LLMClient("http://fake", "key", "model")

    async def run():
        with patch.object(client._client, "stream", side_effect=_make_stream_cm([], status_code=500)):
            async for _ in client.generate_stream("p", [{"content": "c"}], deadline=9999999):
                pass  # pragma: no cover

    with pytest.raises(LLMUnavailableError, match="Streaming HTTP 500"):
        asyncio.run(run())


def test_empty_deltas_are_skipped():
    """Chunks with empty or missing delta.content are skipped."""
    lines = [
        _token_line("A"),
        f'data: {json.dumps({"choices": [{"delta": {}}]})}',
        f'data: {json.dumps({"choices": [{"delta": {"content": ""}}]})}',
        _token_line("B"),
        _done_line(),
    ]
    client = _LLMClient("http://fake", "key", "model")

    async def run():
        with patch.object(client._client, "stream", side_effect=_make_stream_cm(lines)):
            return [tok async for tok in client.generate_stream("p", [{"content": "c"}], deadline=9999999)]

    tokens = asyncio.run(run())
    assert tokens == ["A", "B"]
