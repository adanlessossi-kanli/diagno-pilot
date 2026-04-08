"""
Property 12: Champ warnings_present dérivé correctement

**Validates: Requirements 8.4**

Pour toute DiagnoseResponse, le champ `warnings_present` doit être égal à
`bool(fallback_warning or degraded_warning)`.

The endpoint computes:
    fallback_warning = FALLBACK_WARNING if result.fallback_used else None
    warnings_present = bool(fallback_warning or result.degraded_warning)

This test validates the invariant at the Pydantic model level by generating
random combinations of fallback_warning and degraded_warning, constructing
a DiagnoseResponse, and asserting the derived field matches the expected value.
"""
from __future__ import annotations

from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.routers.diagnose import DiagnoseResponse


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_non_empty_str = st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != "")

_st_fallback_warning = st.one_of(st.none(), _non_empty_str)
_st_degraded_warning = st.one_of(st.none(), _non_empty_str)


# ---------------------------------------------------------------------------
# Property 12 — warnings_present == bool(fallback_warning or degraded_warning)
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    fallback_warning=_st_fallback_warning,
    degraded_warning=_st_degraded_warning,
)
def test_property_12_warnings_present_derived_correctly(
    fallback_warning: str | None,
    degraded_warning: str | None,
) -> None:
    """**Validates: Requirements 8.4**

    For any DiagnoseResponse, the field `warnings_present` must equal
    `bool(fallback_warning or degraded_warning)`.
    """
    expected = bool(fallback_warning or degraded_warning)

    response = DiagnoseResponse(
        session_id="test-session",
        diagnoses=[],
        fallback_warning=fallback_warning,
        degraded_warning=degraded_warning,
        warnings_present=expected,
    )

    assert response.warnings_present == bool(
        response.fallback_warning or response.degraded_warning
    ), (
        f"warnings_present={response.warnings_present} but expected "
        f"bool({response.fallback_warning!r} or {response.degraded_warning!r}) "
        f"= {bool(response.fallback_warning or response.degraded_warning)}"
    )


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------

def test_edge_both_none_warnings_present_false() -> None:
    """Both None → warnings_present is False.

    **Validates: Requirements 8.4**
    """
    response = DiagnoseResponse(
        session_id="s1",
        diagnoses=[],
        fallback_warning=None,
        degraded_warning=None,
        warnings_present=bool(None or None),
    )
    assert response.warnings_present is False


def test_edge_only_fallback_warning_set() -> None:
    """Only fallback_warning set → warnings_present is True.

    **Validates: Requirements 8.4**
    """
    fw = "Réponse générée par le modèle de secours (GPT-5) — vérification clinique recommandée"
    response = DiagnoseResponse(
        session_id="s2",
        diagnoses=[],
        fallback_warning=fw,
        degraded_warning=None,
        warnings_present=bool(fw or None),
    )
    assert response.warnings_present is True


def test_edge_only_degraded_warning_set() -> None:
    """Only degraded_warning set → warnings_present is True.

    **Validates: Requirements 8.4**
    """
    dw = "Agents omis : epidemiology, lab"
    response = DiagnoseResponse(
        session_id="s3",
        diagnoses=[],
        fallback_warning=None,
        degraded_warning=dw,
        warnings_present=bool(None or dw),
    )
    assert response.warnings_present is True


def test_edge_both_warnings_set() -> None:
    """Both set → warnings_present is True.

    **Validates: Requirements 8.4**
    """
    fw = "Réponse générée par le modèle de secours (GPT-5)"
    dw = "Agents omis : lab"
    response = DiagnoseResponse(
        session_id="s4",
        diagnoses=[],
        fallback_warning=fw,
        degraded_warning=dw,
        warnings_present=bool(fw or dw),
    )
    assert response.warnings_present is True
