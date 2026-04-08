"""
Tests unitaires pour le LLM Router avec intégration BAA — Diagno-Pilot

Vérifie le routage primaire vers Model_Container, le déclenchement du
PHI stripping lors du fallback, et le circuit breaker.

**Validates: Requirements 5.2, 5.3, 5.4**
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.circuit_breaker import CircuitBreaker
from backend.core.retry import LLMUnavailableError
from backend.services.baa_controller import BAAController, BAAStripError
from backend.services.llm_router import LLMRouter
from backend.services.phi_classifier import PHIClassifier


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Test: Primary routing to Model_Container (Req 5.1, 5.2)
# ---------------------------------------------------------------------------


def test_primary_routes_to_model_container():
    """When Model_Container is available, requests go to primary and
    BAA stripping is NOT invoked."""
    baa = MagicMock(spec=BAAController)
    classifier = PHIClassifier()

    router = LLMRouter(
        primary_url="http://model:8080/v1",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
        baa_controller=baa,
        phi_classifier=classifier,
    )

    context = [{"content": "patient data", "full_name": "Jean Dupont"}]

    with patch.object(router._primary, "generate", new=AsyncMock(return_value="diagnosis")):
        result = _run(router.generate("symptoms?", context))

    assert result.answer == "diagnosis"
    assert result.fallback_used is False
    assert router.last_used == "MedicalQwen3-Reasoning-4B"
    # BAA strip should NOT be called for primary
    baa.strip_phi.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Fallback triggers BAA PHI stripping (Req 5.3, 5.4)
# ---------------------------------------------------------------------------


def test_fallback_triggers_baa_phi_stripping():
    """When primary fails, fallback is used and BAA strips PHI from context."""
    classifier = PHIClassifier()
    baa = BAAController()

    router = LLMRouter(
        primary_url="http://model:8080/v1",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
        baa_controller=baa,
        phi_classifier=classifier,
    )

    context = [
        {"content": "check patient", "role": "user", "full_name": "Jean Dupont"},
    ]

    fallback_generate = AsyncMock(return_value="fallback answer")

    with patch.object(router._primary, "generate", side_effect=LLMUnavailableError("down")):
        with patch.object(router._fallback, "generate", fallback_generate):
            result = _run(router.generate("symptoms?", context))

    assert result.answer == "fallback answer"
    assert result.fallback_used is True
    assert router.last_used == "gpt-5"

    # Verify the fallback received stripped context (no PHI)
    call_args = fallback_generate.call_args
    sent_context = call_args[0][1]  # second positional arg is context
    for msg in sent_context:
        if "full_name" in msg:
            assert msg["full_name"] == "[PATIENT_NAME]"


def test_fallback_context_has_no_phi_values():
    """The context sent to GPT-5 fallback must contain zero PHI values."""
    classifier = PHIClassifier()
    baa = BAAController()

    router = LLMRouter(
        primary_url="http://model:8080/v1",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
        baa_controller=baa,
        phi_classifier=classifier,
    )

    phi_context = [
        {
            "content": "evaluate",
            "role": "system",
            "full_name": "Marie Kokou",
            "date_of_birth": "1990-05-12",
            "medical_record_number": "MRN-999",
            "allergies": "Pénicilline",
        },
    ]

    captured_context = []

    async def capture_fallback(prompt, context, *, deadline):
        captured_context.extend(context)
        return "ok"

    with patch.object(router._primary, "generate", side_effect=LLMUnavailableError("down")):
        with patch.object(router._fallback, "generate", capture_fallback):
            _run(router.generate("test", phi_context))

    # Verify no original PHI values in the captured context
    original_phi = {"Marie Kokou", "1990-05-12", "MRN-999", "Pénicilline"}
    for msg in captured_context:
        for val in msg.values():
            if isinstance(val, str):
                assert val not in original_phi, f"PHI value '{val}' leaked to fallback"


# ---------------------------------------------------------------------------
# Test: BAA strip failure blocks external call (Req 9.4)
# ---------------------------------------------------------------------------


def test_baa_strip_failure_blocks_external_call():
    """If BAA PHI stripping fails, the external LLM call is blocked with 503."""
    from fastapi import HTTPException

    baa = MagicMock(spec=BAAController)
    baa.strip_phi.side_effect = BAAStripError("strip failed")
    classifier = PHIClassifier()

    router = LLMRouter(
        primary_url="http://model:8080/v1",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
        baa_controller=baa,
        phi_classifier=classifier,
    )

    with patch.object(router._primary, "generate", side_effect=LLMUnavailableError("down")):
        with pytest.raises(HTTPException) as exc_info:
            _run(router.generate("test", [{"content": "data"}]))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "PHI_STRIP_FAILED"
    assert exc_info.value.detail["retryable"] is False


# ---------------------------------------------------------------------------
# Test: Circuit breaker opens after 5 failures (Req 5.2)
# ---------------------------------------------------------------------------


def test_circuit_breaker_opens_after_5_failures():
    """After 5 consecutive primary failures, the circuit opens and
    subsequent requests skip directly to fallback."""
    cb = CircuitBreaker(failure_threshold=5, recovery_timeout=9999)
    router = LLMRouter(
        primary_url="http://model:8080/v1",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
        circuit_breaker=cb,
    )

    async def run_test():
        # Fail primary 5 times to open the circuit
        for _ in range(5):
            with patch.object(router._primary, "generate", side_effect=LLMUnavailableError("fail")):
                with patch.object(router._fallback, "generate", new=AsyncMock(return_value="fb")):
                    result = await router.generate("test", [])
                    assert result.fallback_used is True

        # Circuit should now be open
        from backend.core.circuit_breaker import CircuitState
        assert cb.state == CircuitState.OPEN

        # Next call should skip primary entirely
        primary_mock = AsyncMock(side_effect=AssertionError("primary should not be called"))
        with patch.object(router._primary, "generate", primary_mock):
            with patch.object(router._fallback, "generate", new=AsyncMock(return_value="skipped")):
                result = await router.generate("test", [])
                assert result.fallback_used is True
                assert result.answer == "skipped"

        primary_mock.assert_not_called()

    _run(run_test())


# ---------------------------------------------------------------------------
# Test: Without BAA controller, fallback works as before (backward compat)
# ---------------------------------------------------------------------------


def test_fallback_works_without_baa_controller():
    """When no BAA controller is configured, fallback sends context as-is
    (backward compatibility)."""
    router = LLMRouter(
        primary_url="http://model:8080/v1",
        primary_api_key="key",
        fallback_url="http://fallback",
        fallback_api_key="key",
    )

    context = [{"content": "data", "full_name": "Test"}]

    captured = []

    async def capture(prompt, ctx, *, deadline):
        captured.extend(ctx)
        return "answer"

    with patch.object(router._primary, "generate", side_effect=LLMUnavailableError("down")):
        with patch.object(router._fallback, "generate", capture):
            result = _run(router.generate("test", context))

    assert result.fallback_used is True
    # Context passed through unmodified
    assert captured[0]["full_name"] == "Test"


# ---------------------------------------------------------------------------
# Test: PRIMARY_MODEL updated to MedicalQwen3-Reasoning-4B (Req 5.1)
# ---------------------------------------------------------------------------


def test_primary_model_name_updated():
    """PRIMARY_MODEL should be MedicalQwen3-Reasoning-4B."""
    assert LLMRouter.PRIMARY_MODEL == "MedicalQwen3-Reasoning-4B"
