# Feature: llm-response-streaming, Property 2: Pre-Token Fallback with PHI Stripping
# Feature: llm-response-streaming, Property 3: No Mid-Stream Fallback
"""
Property 2: Pre-Token Fallback with PHI Stripping

For any prompt and context list, when the primary LLM fails (via
LLMUnavailableError or CircuitOpenError) before any tokens have been yielded,
LLMRouter.generate_stream() SHALL invoke BAA_Controller.strip_phi() on the
context and then yield token chunks from the fallback (GPT-5) LLM client's
streaming response.

Validates: Requirements 2.2, 2.4

Property 3: No Mid-Stream Fallback

For any positive number of tokens already yielded from the primary LLM during
LLMRouter.generate_stream(), if the primary LLM fails after those tokens have
been yielded, the router SHALL NOT invoke the fallback LLM and SHALL instead
yield a StreamChunk with a non-None error field.

Validates: Requirement 2.3
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.core.circuit_breaker import CircuitBreaker
from backend.core.retry import LLMUnavailableError
from backend.services.llm_router import LLMRouter


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_prompt_strategy = st.text(min_size=1, max_size=100, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
    blacklist_characters=("\x00",),
))

_context_strategy = st.lists(
    st.fixed_dictionaries({
        "content": st.text(min_size=1, max_size=50),
        "role": st.sampled_from(["system", "user"]),
    }),
    min_size=1,
    max_size=5,
)

_token_strategy = st.text(min_size=1, max_size=30, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
    blacklist_characters=("\x00",),
))


# ---------------------------------------------------------------------------
# Shared router fixture (avoids SSL context creation per iteration)
# ---------------------------------------------------------------------------

def _make_router(baa=None, classifier=None, cb=None):
    """Create a router with mocked HTTP clients to avoid SSL overhead."""
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
# Property 2: Pre-Token Fallback with PHI Stripping
# ---------------------------------------------------------------------------

@given(
    prompt=_prompt_strategy,
    context=_context_strategy,
    fallback_tokens=st.lists(_token_strategy, min_size=1, max_size=10),
)
@h_settings(max_examples=100, deadline=None)
def test_pre_token_fallback_strips_phi_and_uses_fallback(
    prompt: str,
    context: list[dict],
    fallback_tokens: list[str],
):
    """
    # Feature: llm-response-streaming, Property 2: Pre-Token Fallback with PHI Stripping

    When primary fails before any tokens, BAA_Controller.strip_phi is called
    and fallback's generate_stream is invoked with the sanitized context.
    """
    baa = MagicMock()
    stripped_context = [{"content": "[REDACTED]", "role": "system"}]
    baa.strip_phi.return_value = stripped_context
    classifier = MagicMock()

    router = _make_router(baa=baa, classifier=classifier)

    captured_context = []

    async def failing_primary(p, ctx, *, deadline):
        raise LLMUnavailableError("primary down")
        yield ""  # pragma: no cover

    async def fake_fallback(p, ctx, *, deadline):
        captured_context.append(ctx)
        for t in fallback_tokens:
            yield t

    router._primary.generate_stream = failing_primary
    router._fallback.generate_stream = fake_fallback

    async def run():
        chunks = []
        async for chunk in router.generate_stream(prompt, context):
            chunks.append(chunk)
        return chunks

    chunks = _run(run())

    # BAA strip_phi must have been called with the original context
    baa.strip_phi.assert_called_once_with(context, classifier)

    # Fallback must have received the stripped context
    assert len(captured_context) == 1
    assert captured_context[0] is stripped_context

    # All chunks should be from fallback with correct metadata
    token_chunks = [c for c in chunks if c.token is not None]
    assert [c.token for c in token_chunks] == fallback_tokens
    for c in token_chunks:
        assert c.fallback_used is True
        assert c.llm_used == "gpt-5"


@given(
    prompt=_prompt_strategy,
    context=_context_strategy,
    fallback_tokens=st.lists(_token_strategy, min_size=1, max_size=10),
)
@h_settings(max_examples=100, deadline=None)
def test_circuit_open_skips_to_fallback_with_phi_stripping(
    prompt: str,
    context: list[dict],
    fallback_tokens: list[str],
):
    """
    # Feature: llm-response-streaming, Property 2: Pre-Token Fallback with PHI Stripping

    When the primary circuit breaker is OPEN, the router skips directly to
    fallback with PHI stripping — primary generate_stream is never called.
    """
    baa = MagicMock()
    stripped_context = [{"content": "[REDACTED]", "role": "system"}]
    baa.strip_phi.return_value = stripped_context
    classifier = MagicMock()

    # Create a circuit breaker that's already open
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)

    router = _make_router(baa=baa, classifier=classifier, cb=cb)

    primary_called = False

    async def should_not_be_called(*args, **kwargs):
        nonlocal primary_called
        primary_called = True
        yield ""  # pragma: no cover

    async def fake_fallback(p, ctx, *, deadline):
        for t in fallback_tokens:
            yield t

    router._primary.generate_stream = should_not_be_called
    router._fallback.generate_stream = fake_fallback

    async def run():
        # Trip the circuit breaker
        async with cb._lock:
            cb._failure_count = cb.failure_threshold
            cb._trip()

        chunks = []
        async for chunk in router.generate_stream(prompt, context):
            chunks.append(chunk)
        return chunks

    chunks = _run(run())

    assert not primary_called
    baa.strip_phi.assert_called_once_with(context, classifier)
    token_chunks = [c for c in chunks if c.token is not None]
    assert [c.token for c in token_chunks] == fallback_tokens


# ---------------------------------------------------------------------------
# Property 3: No Mid-Stream Fallback
# ---------------------------------------------------------------------------

@given(
    num_tokens=st.integers(min_value=1, max_value=50),
)
@h_settings(max_examples=100, deadline=None)
def test_no_mid_stream_fallback(num_tokens: int):
    """
    # Feature: llm-response-streaming, Property 3: No Mid-Stream Fallback

    When the primary LLM fails after yielding tokens, the router does NOT
    invoke the fallback and instead yields a StreamChunk with error set.
    """
    router = _make_router()

    fallback_called = False

    async def primary_yields_then_fails(p, ctx, *, deadline):
        for i in range(num_tokens):
            yield f"tok{i}"
        raise LLMUnavailableError("mid-stream failure")

    async def fallback_should_not_be_called(*args, **kwargs):
        nonlocal fallback_called
        fallback_called = True
        yield ""  # pragma: no cover

    router._primary.generate_stream = primary_yields_then_fails
    router._fallback.generate_stream = fallback_should_not_be_called

    async def run():
        chunks = []
        async for chunk in router.generate_stream("prompt", [{"content": "ctx"}]):
            chunks.append(chunk)
        return chunks

    chunks = _run(run())

    # Fallback must never be called
    assert not fallback_called

    # Should have num_tokens token chunks + 1 error chunk
    token_chunks = [c for c in chunks if c.token is not None]
    error_chunks = [c for c in chunks if c.error is not None]

    assert len(token_chunks) == num_tokens
    assert [c.token for c in token_chunks] == [f"tok{i}" for i in range(num_tokens)]
    assert len(error_chunks) == 1
    assert error_chunks[0].error is not None
    assert error_chunks[0].llm_used == "MedicalQwen3-Reasoning-4B"
