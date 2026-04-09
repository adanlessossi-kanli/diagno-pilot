# Feature: llm-response-streaming, Property 1: LLM Client Stream Parsing
"""
Property 1: LLM Client Stream Parsing

For any sequence of SSE lines from an OpenAI-compatible /chat/completions
streaming response — containing zero or more chunks with non-empty
delta.content, zero or more chunks with empty delta.content, and a terminal
data: [DONE] line — the _LLMClient.generate_stream() async iterator SHALL
yield exactly the non-empty delta.content strings in order and then stop
iteration.

Validates: Requirements 1.1, 1.2, 1.3
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import patch

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.llm_router import _LLMClient


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A single SSE chunk: either a non-empty token, an empty delta, or [DONE].
_token_strategy = st.text(min_size=1, max_size=50, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
    blacklist_characters=("\x00",),
))


@st.composite
def sse_line_sequence(draw):
    """Generate a list of (sse_line_string, expected_token_or_None) tuples.

    The sequence always ends with a [DONE] sentinel.
    """
    # Draw a list of "chunk descriptors": either ("token", text) or ("empty",)
    chunk_types = draw(st.lists(
        st.one_of(
            st.tuples(st.just("token"), _token_strategy),
            st.tuples(st.just("empty")),
        ),
        min_size=0,
        max_size=30,
    ))

    lines: list[str] = []
    expected_tokens: list[str] = []

    for desc in chunk_types:
        if desc[0] == "token":
            token = desc[1]
            chunk_json = json.dumps({
                "choices": [{"delta": {"content": token}}]
            })
            lines.append(f"data: {chunk_json}")
            expected_tokens.append(token)
        else:
            # Empty delta — should be skipped
            chunk_json = json.dumps({
                "choices": [{"delta": {}}]
            })
            lines.append(f"data: {chunk_json}")

    # Terminal sentinel
    lines.append("data: [DONE]")

    return lines, expected_tokens


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeStreamResponse:
    """Mimics an httpx streaming response with aiter_lines()."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aclose(self) -> None:
        pass


def _make_stream_cm(lines: list[str]):
    """Return an async context manager that yields a _FakeStreamResponse."""
    resp = _FakeStreamResponse(lines)

    @asynccontextmanager
    async def _cm(*args, **kwargs):
        yield resp

    return _cm


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(data=sse_line_sequence())
@h_settings(max_examples=100, deadline=None)
def test_generate_stream_yields_exactly_nonempty_tokens(data):
    """
    # Feature: llm-response-streaming, Property 1: LLM Client Stream Parsing

    For any sequence of SSE lines, generate_stream() yields exactly the
    non-empty delta.content strings in order.
    """
    lines, expected_tokens = data

    client = _LLMClient(
        base_url="http://fake-llm",
        api_key="test-key",
        model="test-model",
    )

    async def run():
        with patch.object(client._client, "stream", side_effect=_make_stream_cm(lines)):
            collected = []
            async for token in client.generate_stream("prompt", [{"content": "ctx"}], deadline=9999999):
                collected.append(token)
            return collected

    collected = asyncio.run(run())
    assert collected == expected_tokens
