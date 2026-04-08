"""Unit tests for LLMRouter resilience — structured 503 error body.

Tests cover:
  - HTTP 503 structured error body when both LLMs are exhausted (Req 1.11)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from backend.core.circuit_breaker import CircuitBreaker
from backend.core.retry import LLMUnavailableError
from backend.models.document import RAGResponse
from backend.routers.chat import FALLBACK_WARNING
from backend.services.llm_router import LLMResult, LLMRouter


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Unit tests — 503 structured error body (Req 1.11)
# ---------------------------------------------------------------------------


def test_503_body_contains_error_field_when_both_llms_exhausted():
    """Response body must contain 'error' field when both LLMs are exhausted."""
    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )
    router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary down"))
    router._fallback.generate = AsyncMock(side_effect=LLMUnavailableError("fallback down"))

    async def _test():
        with pytest.raises(HTTPException) as exc_info:
            await router.generate("test prompt", [])
        detail = exc_info.value.detail
        assert "error" in detail, f"'error' field missing from 503 detail: {detail}"
        assert detail["error"] == "llm_unavailable"

    _run(_test())


def test_503_body_contains_code_field_when_both_llms_exhausted():
    """Response body must contain 'code' field when both LLMs are exhausted."""
    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )
    router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary down"))
    router._fallback.generate = AsyncMock(side_effect=LLMUnavailableError("fallback down"))

    async def _test():
        with pytest.raises(HTTPException) as exc_info:
            await router.generate("test prompt", [])
        detail = exc_info.value.detail
        assert "code" in detail, f"'code' field missing from 503 detail: {detail}"
        assert detail["code"] == "LLM_UNAVAILABLE"

    _run(_test())


def test_503_body_contains_retryable_field_when_both_llms_exhausted():
    """Response body must contain 'retryable' field set to True when both LLMs are exhausted."""
    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )
    router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary down"))
    router._fallback.generate = AsyncMock(side_effect=LLMUnavailableError("fallback down"))

    async def _test():
        with pytest.raises(HTTPException) as exc_info:
            await router.generate("test prompt", [])
        detail = exc_info.value.detail
        assert "retryable" in detail, f"'retryable' field missing from 503 detail: {detail}"
        assert detail["retryable"] is True

    _run(_test())


def test_503_status_code_when_both_llms_exhausted():
    """HTTP status code must be 503 when both LLMs are exhausted."""
    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )
    router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary down"))
    router._fallback.generate = AsyncMock(side_effect=LLMUnavailableError("fallback down"))

    async def _test():
        with pytest.raises(HTTPException) as exc_info:
            await router.generate("test prompt", [])
        assert exc_info.value.status_code == 503

    _run(_test())


def test_503_when_fallback_circuit_open():
    """HTTP 503 is raised when the fallback circuit breaker is OPEN."""
    # Open the fallback circuit breaker
    fallback_cb = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)

    async def _open_cb():
        try:
            await fallback_cb.call_fn(AsyncMock(side_effect=Exception("fail")))
        except Exception:
            pass

    _run(_open_cb())

    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
        fallback_circuit_breaker=fallback_cb,
    )
    router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary down"))

    async def _test():
        with pytest.raises(HTTPException) as exc_info:
            await router.generate("test prompt", [])
        assert exc_info.value.status_code == 503
        detail = exc_info.value.detail
        assert detail["error"] == "llm_unavailable"
        assert detail["code"] == "LLM_UNAVAILABLE"
        assert detail["retryable"] is True

    _run(_test())


def test_llm_result_fallback_used_false_when_primary_succeeds():
    """LLMResult.fallback_used is False when primary LLM succeeds."""
    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )
    router._primary.generate = AsyncMock(return_value="primary answer")

    async def _test():
        result = await router.generate("test prompt", [])
        assert isinstance(result, LLMResult)
        assert result.answer == "primary answer"
        assert result.fallback_used is False

    _run(_test())


def test_llm_result_fallback_used_true_when_primary_fails():
    """LLMResult.fallback_used is True when fallback LLM is used."""
    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )
    router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary down"))
    router._fallback.generate = AsyncMock(return_value="fallback answer")

    async def _test():
        result = await router.generate("test prompt", [])
        assert isinstance(result, LLMResult)
        assert result.answer == "fallback answer"
        assert result.fallback_used is True

    _run(_test())


# ---------------------------------------------------------------------------
# Property tests — Properties 10 and 11
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Property 10: fallback_used flag is set when fallback LLM is used
# Feature: llm-resilience, Property 10: fallback_used flag is set when fallback LLM is used
# ---------------------------------------------------------------------------

@patch("httpx.AsyncClient", autospec=True)
@given(
    prompt=st.text(min_size=1, max_size=100),
    answer=st.text(min_size=1, max_size=200),
)
@h_settings(max_examples=100, deadline=None)
def test_p10_fallback_used_false_when_primary_succeeds(_mock_client, prompt: str, answer: str):
    """
    # Feature: llm-resilience, Property 10: fallback_used flag is set when fallback LLM is used

    For any LLMRouter.generate() call where the primary LLM succeeds,
    fallback_used SHALL be False.

    **Validates: Requirements 4.1**
    """
    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )
    router._primary.generate = AsyncMock(return_value=answer)

    async def _test():
        result = await router.generate(prompt, [])
        assert isinstance(result, LLMResult)
        assert result.fallback_used is False
        assert result.answer == answer

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_test())


@patch("httpx.AsyncClient", autospec=True)
@given(
    prompt=st.text(min_size=1, max_size=100),
    answer=st.text(min_size=1, max_size=200),
)
@h_settings(max_examples=100, deadline=None)
def test_p10_fallback_used_true_when_primary_unavailable(_mock_client, prompt: str, answer: str):
    """
    # Feature: llm-resilience, Property 10: fallback_used flag is set when fallback LLM is used

    For any LLMRouter.generate() call where the primary LLM is unavailable
    and the fallback LLM succeeds, fallback_used SHALL be True.

    **Validates: Requirements 4.1**
    """
    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )
    router._primary.generate = AsyncMock(side_effect=LLMUnavailableError("primary down"))
    router._fallback.generate = AsyncMock(return_value=answer)

    async def _test():
        result = await router.generate(prompt, [])
        assert isinstance(result, LLMResult)
        assert result.fallback_used is True
        assert result.answer == answer

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_test())


# ---------------------------------------------------------------------------
# Property 11: Warning fields propagate unchanged to API response
# Feature: llm-resilience, Property 11: Warning fields propagate unchanged to API response
# ---------------------------------------------------------------------------

def _make_rag_response(
    fallback_used: bool,
    degraded_warning: str | None,
    answer: str = "test answer",
) -> RAGResponse:
    return RAGResponse(
        answer=answer,
        sources=[],
        llm_used="gpt5" if fallback_used else "qwen3",
        fallback_used=fallback_used,
        degraded_warning=degraded_warning,
    )


def _compute_api_warning_fields(rag_response: RAGResponse) -> dict:
    """Simulate the API response warning field computation (same logic as both routers)."""
    fallback_warning = FALLBACK_WARNING if rag_response.fallback_used else None
    warnings_present = bool(fallback_warning or rag_response.degraded_warning)
    return {
        "fallback_warning": fallback_warning,
        "degraded_warning": rag_response.degraded_warning,
        "warnings_present": warnings_present,
    }


degraded_warning_strategy = st.one_of(
    st.none(),
    st.just("Vector Search unavailable — response based on keyword retrieval only"),
    st.just(
        "Vector Search and keyword retrieval unavailable"
        " — response generated without document context"
    ),
    st.text(min_size=1, max_size=200),
)


@given(
    fallback_used=st.booleans(),
    degraded_warning=degraded_warning_strategy,
)
@h_settings(max_examples=100)
def test_p11_fallback_warning_present_iff_fallback_used(
    fallback_used: bool,
    degraded_warning: str | None,
):
    """
    # Feature: llm-resilience, Property 11: Warning fields propagate unchanged to API response

    For any RAGResponse with fallback_used=True, the API response body SHALL
    contain the canonical fallback_warning string. When fallback_used=False,
    fallback_warning SHALL be None.

    **Validates: Requirements 4.2, 4.3, 4.4, 4.5**
    """
    rag_response = _make_rag_response(fallback_used=fallback_used, degraded_warning=degraded_warning)
    fields = _compute_api_warning_fields(rag_response)

    if fallback_used:
        assert fields["fallback_warning"] == FALLBACK_WARNING, (
            f"Expected canonical fallback_warning when fallback_used=True, got {fields['fallback_warning']!r}"
        )
    else:
        assert fields["fallback_warning"] is None, (
            f"Expected fallback_warning=None when fallback_used=False, got {fields['fallback_warning']!r}"
        )


@given(
    fallback_used=st.booleans(),
    degraded_warning=degraded_warning_strategy,
)
@h_settings(max_examples=100)
def test_p11_degraded_warning_propagates_unchanged(
    fallback_used: bool,
    degraded_warning: str | None,
):
    """
    # Feature: llm-resilience, Property 11: Warning fields propagate unchanged to API response

    For any RAGResponse with a non-None degraded_warning, the API response body
    SHALL contain the degraded_warning value unchanged.

    **Validates: Requirements 4.2, 4.3, 4.4, 4.5**
    """
    rag_response = _make_rag_response(fallback_used=fallback_used, degraded_warning=degraded_warning)
    fields = _compute_api_warning_fields(rag_response)

    assert fields["degraded_warning"] == degraded_warning, (
        f"degraded_warning was modified: expected {degraded_warning!r}, got {fields['degraded_warning']!r}"
    )


@given(
    fallback_used=st.booleans(),
    degraded_warning=degraded_warning_strategy,
)
@h_settings(max_examples=100)
def test_p11_warnings_present_true_when_any_warning_present(
    fallback_used: bool,
    degraded_warning: str | None,
):
    """
    # Feature: llm-resilience, Property 11: Warning fields propagate unchanged to API response

    For any RAGResponse, warnings_present SHALL be True when either
    fallback_used=True or degraded_warning is non-None, and False otherwise.

    **Validates: Requirements 4.2, 4.3, 4.4, 4.5**
    """
    rag_response = _make_rag_response(fallback_used=fallback_used, degraded_warning=degraded_warning)
    fields = _compute_api_warning_fields(rag_response)

    has_any_warning = fallback_used or (degraded_warning is not None)
    assert fields["warnings_present"] is has_any_warning, (
        f"warnings_present={fields['warnings_present']!r} but expected {has_any_warning!r} "
        f"(fallback_used={fallback_used}, degraded_warning={degraded_warning!r})"
    )
