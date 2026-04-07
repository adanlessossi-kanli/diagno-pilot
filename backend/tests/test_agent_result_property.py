"""
Property-based tests for AgentResult structural invariant.

Feature: guided-diagnosis-multi-agent, Property 5: Invariant structurel des AgentResult

**Validates: Requirements 4.5, 4.6**

Property 5: For ALL AgentResult produced by an MCP specialist server:
- confidence_score must be in [0.0, 1.0]
- Each element of partial_differential must contain:
  - condition: non-empty string
  - probability: in [0.0, 1.0]
  - icd_code: optional (string or null)
  - matching_symptoms: a list
"""
from __future__ import annotations

from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.models.consultation import DifferentialDiagnosis
from backend.services.mcp_host import AgentResult


# ---------------------------------------------------------------------------
# Reusable strategies (aligned with test_mcp_serialization_property.py)
# ---------------------------------------------------------------------------

_st_text = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
)

_st_icd_code = st.one_of(
    st.none(),
    st.from_regex(r"[A-Z][0-9]{2}(\.[0-9]{1,2})?", fullmatch=True),
)

_st_differential_diagnosis = st.builds(
    DifferentialDiagnosis,
    condition=_st_text,
    probability=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    icd_code=_st_icd_code,
    matching_symptoms=st.lists(_st_text, min_size=0, max_size=5),
)

_st_chunk = st.fixed_dictionaries({
    "document_id": _st_text,
    "title": _st_text,
    "source": _st_text,
    "excerpt": _st_text,
    "page": st.one_of(st.none(), st.integers(min_value=1, max_value=500)),
})

_st_agent_result = st.builds(
    AgentResult,
    agent_name=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))),
    sub_question=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"))),
    chunks=st.lists(_st_chunk, min_size=0, max_size=5),
    confidence_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    partial_differential=st.lists(_st_differential_diagnosis, min_size=0, max_size=5),
    timed_out=st.booleans(),
    omitted=st.booleans(),
    fallback_used=st.booleans(),
)

# ---------------------------------------------------------------------------
# Dict-based strategies (matching AgentResult JSON schema from design doc)
# ---------------------------------------------------------------------------

_st_partial_diag_dict = st.fixed_dictionaries({
    "condition": _st_text,
    "probability": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "icd_code": st.one_of(st.none(), st.from_regex(r"[A-Z][0-9]{2}(\.[0-9]{1,2})?", fullmatch=True)),
    "matching_symptoms": st.lists(_st_text, min_size=0, max_size=5),
})

_st_agent_result_dict = st.fixed_dictionaries({
    "agent_name": _st_text,
    "sub_question": _st_text,
    "chunks": st.lists(_st_chunk, min_size=0, max_size=5),
    "confidence_score": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "partial_differential": st.lists(_st_partial_diag_dict, min_size=0, max_size=5),
    "fallback_used": st.booleans(),
})


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent, Property 5: Invariant structurel des AgentResult
# ---------------------------------------------------------------------------


@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(agent_result=_st_agent_result)
def test_property_5_agent_result_structural_invariant(
    agent_result: AgentResult,
) -> None:
    """Validates: Requirements 4.5, 4.6

    For any AgentResult dataclass instance produced by an MCP specialist server:
    - confidence_score is in [0.0, 1.0]
    - Each partial_differential element has a non-empty condition, probability
      in [0.0, 1.0], icd_code that is string or None, and matching_symptoms
      that is a list.
    """
    # confidence_score in [0.0, 1.0]
    assert 0.0 <= agent_result.confidence_score <= 1.0, (
        f"confidence_score {agent_result.confidence_score} not in [0.0, 1.0]"
    )

    for i, diag in enumerate(agent_result.partial_differential):
        # condition: non-empty string
        assert isinstance(diag.condition, str) and len(diag.condition) > 0, (
            f"partial_differential[{i}].condition must be a non-empty string, "
            f"got {diag.condition!r}"
        )

        # probability in [0.0, 1.0]
        assert 0.0 <= diag.probability <= 1.0, (
            f"partial_differential[{i}].probability {diag.probability} not in [0.0, 1.0]"
        )

        # icd_code: optional (string or null)
        assert diag.icd_code is None or isinstance(diag.icd_code, str), (
            f"partial_differential[{i}].icd_code must be str or None, "
            f"got {type(diag.icd_code)}"
        )

        # matching_symptoms: a list
        assert isinstance(diag.matching_symptoms, list), (
            f"partial_differential[{i}].matching_symptoms must be a list, "
            f"got {type(diag.matching_symptoms)}"
        )


@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(result_dict=_st_agent_result_dict)
def test_property_5_agent_result_dict_structural_invariant(
    result_dict: dict,
) -> None:
    """Validates: Requirements 4.5, 4.6

    For any AgentResult-like dict (as returned by MCP server tool handlers):
    - confidence_score is in [0.0, 1.0]
    - Each partial_differential element has a non-empty condition, probability
      in [0.0, 1.0], icd_code that is string or None, and matching_symptoms
      that is a list.
    """
    # confidence_score in [0.0, 1.0]
    cs = result_dict["confidence_score"]
    assert isinstance(cs, float) and 0.0 <= cs <= 1.0, (
        f"confidence_score {cs} not a float in [0.0, 1.0]"
    )

    for i, diag in enumerate(result_dict["partial_differential"]):
        # condition: non-empty string
        assert isinstance(diag["condition"], str) and len(diag["condition"]) > 0, (
            f"partial_differential[{i}].condition must be a non-empty string, "
            f"got {diag['condition']!r}"
        )

        # probability in [0.0, 1.0]
        prob = diag["probability"]
        assert isinstance(prob, float) and 0.0 <= prob <= 1.0, (
            f"partial_differential[{i}].probability {prob} not a float in [0.0, 1.0]"
        )

        # icd_code: optional (string or null)
        icd = diag["icd_code"]
        assert icd is None or isinstance(icd, str), (
            f"partial_differential[{i}].icd_code must be str or None, "
            f"got {type(icd)}"
        )

        # matching_symptoms: a list
        ms = diag["matching_symptoms"]
        assert isinstance(ms, list), (
            f"partial_differential[{i}].matching_symptoms must be a list, "
            f"got {type(ms)}"
        )
