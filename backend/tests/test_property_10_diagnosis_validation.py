"""
Property 10: Diagnosis input validation

**Validates: Requirements 16.1, 16.2, 16.3, 16.4**

Tests that:
1. DiagnoseRequest accepts iff 1 ≤ len(symptoms) ≤ 30 and all name lengths ≤ 200
2. Requests violating these constraints are rejected with ValidationError (HTTP 422)
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.routers.diagnose import DiagnoseRequest


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_st_valid_name = st.text(min_size=1, max_size=200, alphabet=st.characters(blacklist_categories=("Cs",)))
_st_long_name = st.text(min_size=201, max_size=300, alphabet=st.characters(blacklist_categories=("Cs",)))

_st_valid_symptom = _st_valid_name.map(lambda n: {"name": n})

_st_valid_symptoms_list = st.lists(_st_valid_symptom, min_size=1, max_size=30)


# ---------------------------------------------------------------------------
# Property 10.1 — Valid requests are accepted
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(symptoms=_st_valid_symptoms_list)
def test_property_10_valid_requests_accepted(symptoms: list[dict]) -> None:
    """**Validates: Requirements 16.1, 16.2, 16.3**

    DiagnoseRequest accepts when 1 ≤ len(symptoms) ≤ 30 and all names ≤ 200 chars.
    """
    req = DiagnoseRequest(symptoms=symptoms)
    assert 1 <= len(req.symptoms) <= 30
    for s in req.symptoms:
        assert len(s.name) <= 200


# ---------------------------------------------------------------------------
# Property 10.2 — Empty symptoms list is rejected
# ---------------------------------------------------------------------------

def test_property_10_empty_symptoms_rejected() -> None:
    """**Validates: Requirements 16.1, 16.4**

    Empty symptoms list is rejected with ValidationError.
    """
    with pytest.raises(ValidationError):
        DiagnoseRequest(symptoms=[])


# ---------------------------------------------------------------------------
# Property 10.3 — Too many symptoms rejected
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    count=st.integers(min_value=31, max_value=50),
)
def test_property_10_too_many_symptoms_rejected(count: int) -> None:
    """**Validates: Requirements 16.2, 16.4**

    Symptom lists exceeding 30 entries are rejected with ValidationError.
    """
    symptoms = [{"name": f"symptom_{i}"} for i in range(count)]
    with pytest.raises(ValidationError):
        DiagnoseRequest(symptoms=symptoms)


# ---------------------------------------------------------------------------
# Property 10.4 — Symptom name exceeding 200 chars is rejected
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(long_name=_st_long_name)
def test_property_10_long_symptom_name_rejected(long_name: str) -> None:
    """**Validates: Requirements 16.3, 16.4**

    Symptom names exceeding 200 characters are rejected with ValidationError.
    """
    with pytest.raises(ValidationError):
        DiagnoseRequest(symptoms=[{"name": long_name}])
