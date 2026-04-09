"""Unit tests for LLMRouter.generate_stream().

Validates: Requirements 2.1, 2.5, 2.6
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.core.circuit_breaker import CircuitBreaker
from backend.core.retry import LLMUnavailableError
from backend.services.llm_router import LLMRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_router(baa=None, classifier=None, cb=None):
    """Create a router with mocked internals (no real HTTP clients)."""
    router = LLMRouter.__new__(LLMRouter)
    router._primary = MagicMock()
    router._fallback = MagicMock()
    router._primary_cb = cb or CircuitBreaker(service_name="qwen3")
    router._fallback_cb = CircuitBreaker()
    router._baa_controller = baa
    router._phi_classifier = classifier
    router.last_used = ""
    return router


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Test: Happy path yields primary tokens with correct llm_used
# ---------------------------------------------------------------------------

def test_happy_path_yields_primary_tokens():
    """Primary stream succeeds — yields StreamChunks with correct llm_used."""
    router = _make_router()

    async def primary_stream(p, ctx, *, deadline):
        for tok in ["Hello", " ", "world"]:
            yield tok

    router._primary.generate_stream = primary_stream

    async def run():
        chunks = []
        async for chunk in router.generate_stream("prompt", [{"content": "ctx"}]):
            chunks.append(chunk)
        return chunks

    chunks = _run(run())

    assert len(chunks) == 3
    assert [c.token for c in chunks] == ["Hello", " ", "world"]
    for c in chunks:
        assert c.llm_used == "MedicalQwen3-Reasoning-4B"
        assert c.fallback_used is False
        assert c.error is None
    assert router.last_used == "MedicalQwen3-Reasoning-4B"


# ---------------------------------------------------------------------------
# Test: Both-fail raises HTTP 503
# ---------------------------------------------------------------------------

def test_both_fail_raises_503():
    """When both primary and fallback fail, HTTP 503 is raised."""
    router = _make_router()

    async def failing_stream(*args, **kwargs):
        raise LLMUnavailableError("down")
        yield ""  # pragma: no cover

    router._primary.generate_stream = failing_stream
    router._fallback.generate_stream = failing_stream

    async def run():
        chunks = []
        async for chunk in router.generate_stream("prompt", [{"content": "ctx"}]):
            chunks.append(chunk)

    with pytest.raises(HTTPException) as exc_info:
        _run(run())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "LLM_UNAVAILABLE"
    assert exc_info.value.detail["retryable"] is True


# ---------------------------------------------------------------------------
# Test: Prometheus metrics are recorded on success
# ---------------------------------------------------------------------------

def test_prometheus_metrics_recorded_on_primary_success():
    """Prometheus duration and request count are recorded on primary success."""
    from unittest.mock import patch
    from backend.core.metrics import llm_duration_seconds, llm_requests_total

    router = _make_router()

    async def primary_stream(p, ctx, *, deadline):
        yield "tok"

    router._primary.generate_stream = primary_stream

    with patch.object(
        llm_duration_seconds.labels(model="MedicalQwen3-Reasoning-4B", status="success"),
        "observe",
    ) as mock_observe, patch.object(
        llm_requests_total.labels(model="MedicalQwen3-Reasoning-4B", status="success"),
        "inc",
    ) as mock_inc:
        async def run():
            async for _ in router.generate_stream("p", [{"content": "c"}]):
                pass

        _run(run())

        mock_observe.assert_called_once()
        mock_inc.assert_called_once()


def test_prometheus_metrics_recorded_on_primary_error():
    """Prometheus error metrics are recorded when primary fails pre-token."""
    from unittest.mock import patch
    from backend.core.metrics import llm_duration_seconds, llm_requests_total

    router = _make_router()

    async def failing_primary(*args, **kwargs):
        raise LLMUnavailableError("down")
        yield ""  # pragma: no cover

    async def fallback_stream(*args, **kwargs):
        yield "fb"

    router._primary.generate_stream = failing_primary
    router._fallback.generate_stream = fallback_stream

    with patch.object(
        llm_duration_seconds.labels(model="MedicalQwen3-Reasoning-4B", status="error"),
        "observe",
    ) as mock_observe, patch.object(
        llm_requests_total.labels(model="MedicalQwen3-Reasoning-4B", status="error"),
        "inc",
    ) as mock_inc:
        async def run():
            async for _ in router.generate_stream("p", [{"content": "c"}]):
                pass

        _run(run())

        mock_observe.assert_called_once()
        mock_inc.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Fallback yields tokens with fallback_used=True
# ---------------------------------------------------------------------------

def test_fallback_yields_tokens_with_fallback_used():
    """When primary fails pre-token, fallback tokens have fallback_used=True."""
    router = _make_router()

    async def failing_primary(*args, **kwargs):
        raise LLMUnavailableError("down")
        yield ""  # pragma: no cover

    async def fallback_stream(p, ctx, *, deadline):
        for tok in ["fall", "back"]:
            yield tok

    router._primary.generate_stream = failing_primary
    router._fallback.generate_stream = fallback_stream

    async def run():
        chunks = []
        async for chunk in router.generate_stream("p", [{"content": "c"}]):
            chunks.append(chunk)
        return chunks

    chunks = _run(run())

    assert [c.token for c in chunks] == ["fall", "back"]
    for c in chunks:
        assert c.fallback_used is True
        assert c.llm_used == "gpt-5"


# ---------------------------------------------------------------------------
# Test: Mid-stream error yields error chunk, no fallback
# ---------------------------------------------------------------------------

def test_mid_stream_error_yields_error_chunk():
    """Primary fails after tokens — error chunk emitted, no fallback."""
    router = _make_router()

    async def primary_then_fail(p, ctx, *, deadline):
        yield "partial"
        raise LLMUnavailableError("mid-stream")

    fallback_called = False

    async def fallback_should_not_run(*args, **kwargs):
        nonlocal fallback_called
        fallback_called = True
        yield ""  # pragma: no cover

    router._primary.generate_stream = primary_then_fail
    router._fallback.generate_stream = fallback_should_not_run

    async def run():
        chunks = []
        async for chunk in router.generate_stream("p", [{"content": "c"}]):
            chunks.append(chunk)
        return chunks

    chunks = _run(run())

    assert not fallback_called
    assert chunks[0].token == "partial"
    assert chunks[1].error is not None
    assert chunks[1].llm_used == "MedicalQwen3-Reasoning-4B"
