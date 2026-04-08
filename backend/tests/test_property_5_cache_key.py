"""
Property 5: Context-aware cache key determinism and differentiation

**Validates: Requirements 5.1, 5.2, 5.3**

Tests that:
1. Identical inputs (question, context, region, session_history) produce identical keys
2. Differing inputs produce different keys
3. Empty/None history matches legacy format (no history hash component)
"""
from __future__ import annotations

from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.services.llamaindex_pipeline import LlamaIndexPipeline


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_st_question = st.text(min_size=1, max_size=200)
_st_region = st.one_of(st.none(), st.text(min_size=1, max_size=100))
_st_session_history = st.one_of(
    st.none(),
    st.lists(
        st.fixed_dictionaries({
            "role": st.sampled_from(["user", "assistant"]),
            "content": st.text(min_size=1, max_size=200),
        }),
        min_size=1,
        max_size=10,
    ),
)


# ---------------------------------------------------------------------------
# Property 5.1 — Determinism: same inputs → same key
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    question=_st_question,
    region=_st_region,
    session_history=_st_session_history,
)
def test_property_5_determinism(
    question: str,
    region: str | None,
    session_history: list[dict[str, str]] | None,
) -> None:
    """**Validates: Requirements 5.3**

    Identical inputs produce identical cache keys.
    """
    key1 = LlamaIndexPipeline._build_cache_key(
        question, None, region, session_history=session_history,
    )
    key2 = LlamaIndexPipeline._build_cache_key(
        question, None, region, session_history=session_history,
    )
    assert key1 == key2, f"Same inputs produced different keys: {key1!r} != {key2!r}"


# ---------------------------------------------------------------------------
# Property 5.2 — Differentiation: different question → different key
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    q1=_st_question,
    q2=_st_question,
    region=_st_region,
    session_history=_st_session_history,
)
def test_property_5_different_question_different_key(
    q1: str,
    q2: str,
    region: str | None,
    session_history: list[dict[str, str]] | None,
) -> None:
    """**Validates: Requirements 5.1, 5.3**

    Different questions produce different cache keys (assuming they differ).
    """
    from hypothesis import assume
    assume(q1 != q2)

    key1 = LlamaIndexPipeline._build_cache_key(
        q1, None, region, session_history=session_history,
    )
    key2 = LlamaIndexPipeline._build_cache_key(
        q2, None, region, session_history=session_history,
    )
    assert key1 != key2, (
        f"Different questions produced same key: q1={q1!r}, q2={q2!r}, key={key1!r}"
    )


# ---------------------------------------------------------------------------
# Property 5.3 — Differentiation: different history → different key
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    question=_st_question,
    region=_st_region,
    h1=st.lists(
        st.fixed_dictionaries({
            "role": st.sampled_from(["user", "assistant"]),
            "content": st.text(min_size=1, max_size=200),
        }),
        min_size=1,
        max_size=10,
    ),
    h2=st.lists(
        st.fixed_dictionaries({
            "role": st.sampled_from(["user", "assistant"]),
            "content": st.text(min_size=1, max_size=200),
        }),
        min_size=1,
        max_size=10,
    ),
)
def test_property_5_different_history_different_key(
    question: str,
    region: str | None,
    h1: list[dict[str, str]],
    h2: list[dict[str, str]],
) -> None:
    """**Validates: Requirements 5.1**

    Different session histories produce different cache keys.
    """
    from hypothesis import assume
    import json
    assume(json.dumps(h1, sort_keys=True, default=str) != json.dumps(h2, sort_keys=True, default=str))

    key1 = LlamaIndexPipeline._build_cache_key(
        question, None, region, session_history=h1,
    )
    key2 = LlamaIndexPipeline._build_cache_key(
        question, None, region, session_history=h2,
    )
    assert key1 != key2, (
        f"Different histories produced same key: key={key1!r}"
    )


# ---------------------------------------------------------------------------
# Property 5.4 — Legacy compatibility: empty/None history = no hist component
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    question=_st_question,
    region=_st_region,
)
def test_property_5_legacy_compatibility(
    question: str,
    region: str | None,
) -> None:
    """**Validates: Requirements 5.2**

    Empty or None history produces the same key as no history parameter.
    """
    key_none = LlamaIndexPipeline._build_cache_key(
        question, None, region, session_history=None,
    )
    key_empty = LlamaIndexPipeline._build_cache_key(
        question, None, region, session_history=[],
    )
    key_default = LlamaIndexPipeline._build_cache_key(
        question, None, region,
    )

    assert key_none == key_default, (
        f"None history differs from default: {key_none!r} != {key_default!r}"
    )
    assert key_empty == key_default, (
        f"Empty history differs from default: {key_empty!r} != {key_default!r}"
    )
    # Verify no ":hist=" component in legacy keys
    assert ":hist=" not in key_default, (
        f"Legacy key should not contain ':hist=': {key_default!r}"
    )
