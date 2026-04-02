"""
Tests de propriété pour LLMRouter — Diagno-Pilot

**Validates: Requirements REQ-04**

Propriété 4 : Si MedicalQwen3 lève `LLMUnavailableError`, le LLMRouter
retourne toujours une réponse via GPT-5 (fallback).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.llm_router import LLMRouter, LLMUnavailableError

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

prompt_strategy = st.text(min_size=1, max_size=200)
context_strategy = st.lists(
    st.fixed_dictionaries({"content": st.text(min_size=0, max_size=100)}),
    min_size=0,
    max_size=5,
)
response_strategy = st.text(min_size=1, max_size=500)


# ---------------------------------------------------------------------------
# Property 4a : fallback always returns a response when primary fails
# ---------------------------------------------------------------------------

@given(prompt=prompt_strategy, context=context_strategy, fallback_response=response_strategy)
@h_settings(max_examples=100)
def test_fallback_always_returns_response_when_primary_fails(
    prompt: str, context: list[dict], fallback_response: str
):
    """
    **Validates: Requirements REQ-04**

    For any prompt and context, if MedicalQwen3 raises LLMUnavailableError,
    LLMRouter must return a non-empty response from the GPT-5 fallback.
    """
    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )

    async def run():
        with patch.object(router._primary, "generate", side_effect=LLMUnavailableError("down")):
            with patch.object(router._fallback, "generate", new=AsyncMock(return_value=fallback_response)):
                result = await router.generate(prompt, context)
        return result

    result = asyncio.run(run())
    assert result.answer == fallback_response
    assert result.fallback_used is True
    assert router.last_used == LLMRouter.FALLBACK_MODEL


# ---------------------------------------------------------------------------
# Property 4b : primary is used when available (no fallback triggered)
# ---------------------------------------------------------------------------

@given(prompt=prompt_strategy, context=context_strategy, primary_response=response_strategy)
@h_settings(max_examples=100)
def test_primary_used_when_available(
    prompt: str, context: list[dict], primary_response: str
):
    """
    **Validates: Requirements REQ-04**

    When MedicalQwen3 is available, the router returns its response and
    marks last_used as 'qwen3' without calling the fallback.
    """
    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )

    async def run():
        with patch.object(router._primary, "generate", new=AsyncMock(return_value=primary_response)):
            with patch.object(router._fallback, "generate", side_effect=AssertionError("fallback must not be called")):
                result = await router.generate(prompt, context)
        return result

    result = asyncio.run(run())
    assert result.answer == primary_response
    assert result.fallback_used is False
    assert router.last_used == LLMRouter.PRIMARY_MODEL


# ---------------------------------------------------------------------------
# Property 4c : fallback error propagates when both LLMs fail
# ---------------------------------------------------------------------------

@given(prompt=prompt_strategy, context=context_strategy)
@h_settings(max_examples=50)
def test_error_propagates_when_both_llms_fail(prompt: str, context: list[dict]):
    """
    **Validates: Requirements REQ-04, 5.5**

    When both primary and fallback raise LLMUnavailableError, the router
    raises HTTPException(503, "llm_unavailable") — not a raw LLMUnavailableError.
    """
    from fastapi import HTTPException

    router = LLMRouter(
        primary_url="http://primary",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )

    async def run():
        with patch.object(router._primary, "generate", side_effect=LLMUnavailableError("primary down")):
            with patch.object(router._fallback, "generate", side_effect=LLMUnavailableError("fallback down")):
                await router.generate(prompt, context)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {"error": "llm_unavailable", "code": "LLM_UNAVAILABLE", "retryable": True}
