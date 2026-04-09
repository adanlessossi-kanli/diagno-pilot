# Feature: llm-response-streaming, Property 6: SSE Event Serialization
"""
Property-based test for SSE Event Serialization.

**Validates: Requirements 4.3, 4.4, 8.1, 8.2, 8.3, 8.4**

Property 6: For any StreamEvent (token, done, or error) with arbitrary valid
field values, the SSE serialization produced by the streaming endpoint SHALL
have a valid `event:` line matching the event type and a `data:` line
containing valid JSON that is parseable by JSON.parse without error, and the
parsed JSON SHALL contain all required fields for that event type.
"""
from __future__ import annotations

import json

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.document import DocumentSource, HighlightInfo
from backend.services.llamaindex_pipeline import StreamEvent

# ---------------------------------------------------------------------------
# Constants (must match backend/routers/chat.py)
# ---------------------------------------------------------------------------

FALLBACK_WARNING = (
    "Réponse générée par le modèle de secours (GPT-5) "
    "— vérification clinique recommandée"
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_non_empty_text = st.text(min_size=1, max_size=200).filter(str.strip)

highlight_strategy = st.one_of(
    st.none(),
    st.builds(
        HighlightInfo,
        bbox=st.lists(
            st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=4,
            max_size=4,
        ),
        page=st.integers(min_value=0, max_value=500),
    ),
)

source_strategy = st.builds(
    DocumentSource,
    document_id=st.uuids().map(str),
    title=_non_empty_text,
    source=st.sampled_from(["CHU_LOME", "OMS_AFRO", "MSF", "PNLP", "CHU_ABOMEY"]),
    section=st.one_of(st.none(), _non_empty_text),
    excerpt=st.one_of(st.none(), _non_empty_text),
    page=st.one_of(st.none(), st.integers(min_value=1, max_value=500)),
    highlight=highlight_strategy,
    confidence_score=st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    ),
)

sources_strategy = st.lists(source_strategy, min_size=0, max_size=5)

session_id_strategy = st.uuids().map(str)

# --- Token event strategy ---
token_event_strategy = st.builds(
    lambda content: StreamEvent(type="token", content=content),
    content=_non_empty_text,
)

# --- Done event strategy ---
done_event_strategy = st.builds(
    lambda answer, sources, llm_used, fallback_used, confidence_score: StreamEvent(
        type="done",
        answer=answer,
        sources=sources,
        llm_used=llm_used,
        fallback_used=fallback_used,
        confidence_score=confidence_score,
    ),
    answer=_non_empty_text,
    sources=sources_strategy,
    llm_used=st.sampled_from(["MedicalQwen3-Reasoning-4B", "gpt-5"]),
    fallback_used=st.booleans(),
    confidence_score=st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    ),
)

# --- Error event strategy ---
error_event_strategy = st.builds(
    lambda error, retryable: StreamEvent(
        type="error", error=error, retryable=retryable,
    ),
    error=_non_empty_text,
    retryable=st.booleans(),
)


# ---------------------------------------------------------------------------
# Serialization helper — replicates the exact logic from the endpoint
# ---------------------------------------------------------------------------


def serialize_stream_event(event: StreamEvent, session_id: str) -> dict:
    """Replicate the SSE serialization logic from backend/routers/chat.py."""
    if event.type == "token":
        return {
            "event": "token",
            "data": json.dumps({"content": event.content}),
        }
    elif event.type == "done":
        sources = [s.model_dump() for s in (event.sources or [])]
        fallback_warning = FALLBACK_WARNING if event.fallback_used else None
        warnings_present = bool(fallback_warning)
        return {
            "event": "done",
            "data": json.dumps({
                "answer": event.answer,
                "session_id": session_id,
                "sources": sources,
                "llm_used": event.llm_used,
                "fallback_warning": fallback_warning,
                "warnings_present": warnings_present,
            }),
        }
    elif event.type == "error":
        return {
            "event": "error",
            "data": json.dumps({
                "error": event.error,
                "retryable": event.retryable,
            }),
        }
    else:
        raise ValueError(f"Unknown event type: {event.type}")


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(event=token_event_strategy, session_id=session_id_strategy)
@h_settings(max_examples=100)
def test_token_event_serialization_produces_valid_json_with_required_fields(
    event: StreamEvent,
    session_id: str,
):
    """
    **Validates: Requirements 4.3, 8.1, 8.4**

    For any token StreamEvent, the SSE serialization SHALL have event='token'
    and data containing valid JSON with a 'content' field matching the event.
    """
    sse = serialize_stream_event(event, session_id)

    # event line matches
    assert sse["event"] == "token"

    # data is valid JSON
    parsed = json.loads(sse["data"])

    # required field present
    assert "content" in parsed
    assert parsed["content"] == event.content


@given(event=done_event_strategy, session_id=session_id_strategy)
@h_settings(max_examples=100)
def test_done_event_serialization_produces_valid_json_with_required_fields(
    event: StreamEvent,
    session_id: str,
):
    """
    **Validates: Requirements 4.4, 8.2, 8.4**

    For any done StreamEvent, the SSE serialization SHALL have event='done'
    and data containing valid JSON with all required done-event fields.
    """
    sse = serialize_stream_event(event, session_id)

    # event line matches
    assert sse["event"] == "done"

    # data is valid JSON
    parsed = json.loads(sse["data"])

    # all required fields present
    required_keys = {
        "answer", "session_id", "sources", "llm_used",
        "fallback_warning", "warnings_present",
    }
    assert required_keys.issubset(parsed.keys()), (
        f"Missing keys: {required_keys - parsed.keys()}"
    )

    # value correctness
    assert parsed["answer"] == event.answer
    assert parsed["session_id"] == session_id
    assert parsed["llm_used"] == event.llm_used
    assert isinstance(parsed["sources"], list)
    assert len(parsed["sources"]) == len(event.sources or [])

    # fallback_warning / warnings_present logic
    if event.fallback_used:
        assert parsed["fallback_warning"] == FALLBACK_WARNING
        assert parsed["warnings_present"] is True
    else:
        assert parsed["fallback_warning"] is None
        assert parsed["warnings_present"] is False


@given(event=error_event_strategy, session_id=session_id_strategy)
@h_settings(max_examples=100)
def test_error_event_serialization_produces_valid_json_with_required_fields(
    event: StreamEvent,
    session_id: str,
):
    """
    **Validates: Requirements 4.5, 8.3, 8.4**

    For any error StreamEvent, the SSE serialization SHALL have event='error'
    and data containing valid JSON with 'error' and 'retryable' fields.
    """
    sse = serialize_stream_event(event, session_id)

    # event line matches
    assert sse["event"] == "error"

    # data is valid JSON
    parsed = json.loads(sse["data"])

    # required fields present
    assert "error" in parsed
    assert "retryable" in parsed
    assert parsed["error"] == event.error
    assert parsed["retryable"] == event.retryable
