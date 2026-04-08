"""
Property test — Chat message validation (Property 6).

Feature: chat-diagnosis-improvements, Property 6: Chat message validation

For any string `message`, the ChatMessageRequest model SHALL accept it if
and only if 1 ≤ len(message.strip()) ≤ 4000. Strings that are empty after
whitespace trimming or exceed 4000 characters SHALL be rejected with HTTP 422.

**Validates: Requirements 6.1, 6.2, 6.3**
"""
from __future__ import annotations

from hypothesis import given, settings as h_settings, assume, HealthCheck
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.routers.chat import ChatMessageRequest


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid messages: after stripping, length is between 1 and 4000
_valid_message = st.text(min_size=1, max_size=4000).filter(
    lambda s: 1 <= len(s.strip()) <= 4000
)

# Messages that are empty or whitespace-only after stripping
_whitespace_only = st.text(
    alphabet=st.sampled_from([" ", "\t", "\n", "\r"]),
    min_size=0,
    max_size=50,
)

# Messages that exceed 4000 characters after stripping
_too_long = st.integers(min_value=4001, max_value=5000).flatmap(
    lambda n: st.just("a" * n)
)


# ---------------------------------------------------------------------------
# Property 6a: Valid messages are accepted
# ---------------------------------------------------------------------------

@given(message=_valid_message)
@h_settings(max_examples=100)
def test_valid_messages_accepted(message: str) -> None:
    """Messages with 1 ≤ len(strip()) ≤ 4000 are accepted."""
    req = ChatMessageRequest(message=message)
    # The stored message should be stripped
    assert req.message == message.strip()
    assert 1 <= len(req.message) <= 4000


# ---------------------------------------------------------------------------
# Property 6b: Whitespace-only or empty messages are rejected
# ---------------------------------------------------------------------------

@given(message=_whitespace_only)
@h_settings(max_examples=100)
def test_whitespace_only_messages_rejected(message: str) -> None:
    """Messages that are empty or whitespace-only after stripping are rejected."""
    assume(len(message.strip()) == 0)
    try:
        ChatMessageRequest(message=message)
        assert False, f"Expected ValidationError for whitespace-only message: {message!r}"
    except ValidationError:
        pass


# ---------------------------------------------------------------------------
# Property 6c: Messages exceeding 4000 characters are rejected
# ---------------------------------------------------------------------------

@given(message=_too_long)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.data_too_large])
def test_too_long_messages_rejected(message: str) -> None:
    """Messages exceeding 4000 characters after stripping are rejected."""
    try:
        ChatMessageRequest(message=message)
        assert False, f"Expected ValidationError for message of length {len(message.strip())}"
    except ValidationError:
        pass
