"""
Property-based tests for MCP payload serialization round-trip.

Feature: guided-diagnosis-multi-agent, Property 1: Sérialisation round-trip

**Validates: Requirements 3.4**

Property 1: For ALL valid AgentResult payloads and for ALL tool invocation
argument dicts, serializing to JSON then deserializing must produce a payload
equivalent to the original.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.models.consultation import DifferentialDiagnosis
from backend.services.mcp_host import AgentResult


# ---------------------------------------------------------------------------
# Strategies
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

# Tool invocation arguments matching the TOOL_INPUT_SCHEMA from the design doc
_st_symptom_dict: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries(
    {
        "name": _st_text,
    },
    optional={
        "severity": st.one_of(st.none(), st.sampled_from(["mild", "moderate", "severe"])),
        "duration_days": st.one_of(st.none(), st.integers(min_value=0, max_value=365)),
    },
)

_st_patient_profile: st.SearchStrategy[dict[str, Any] | None] = st.one_of(
    st.none(),
    st.fixed_dictionaries({
        "full_name": _st_text,
        "age_group": st.one_of(st.none(), st.sampled_from(["infant", "child", "adult", "elderly"])),
        "weight_kg": st.one_of(st.none(), st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False)),
    }),
)

_st_tool_arguments: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries(
    {
        "symptoms": st.lists(_st_symptom_dict, min_size=1, max_size=10),
        "locale": st.sampled_from(["fr-TG", "fr-BJ", "en"]),
    },
    optional={
        "patient_profile": _st_patient_profile,
        "region": st.one_of(st.none(), st.sampled_from(["TG", "BJ"])),
    },
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agent_result_to_dict(ar: AgentResult) -> dict:
    """Convert AgentResult to a JSON-serializable dict.

    Uses dataclasses.asdict for the dataclass fields, then converts
    Pydantic DifferentialDiagnosis instances via model_dump().
    """
    d = dataclasses.asdict(ar)
    d["partial_differential"] = [dd.model_dump() for dd in ar.partial_differential]
    return d


# ---------------------------------------------------------------------------
# Feature: guided-diagnosis-multi-agent, Property 1: Sérialisation round-trip
# ---------------------------------------------------------------------------


@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(agent_result=_st_agent_result)
def test_property_1_serialization_round_trip_agent_result(
    agent_result: AgentResult,
) -> None:
    """Validates: Requirements 3.4

    For any valid AgentResult payload, serializing to JSON then deserializing
    must produce a dict equivalent to the original dataclasses.asdict() output.
    """
    original_dict = _agent_result_to_dict(agent_result)

    serialized = json.dumps(original_dict)
    deserialized = json.loads(serialized)

    assert deserialized == original_dict, (
        f"Round-trip mismatch:\n"
        f"  original:     {original_dict}\n"
        f"  deserialized: {deserialized}"
    )


@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(tool_args=_st_tool_arguments)
def test_property_1_serialization_round_trip_tool_arguments(
    tool_args: dict,
) -> None:
    """Validates: Requirements 3.4

    For any valid tool invocation argument dict (matching the TOOL_INPUT_SCHEMA),
    serializing to JSON then deserializing must produce a dict equivalent to the
    original.
    """
    serialized = json.dumps(tool_args)
    deserialized = json.loads(serialized)

    assert deserialized == tool_args, (
        f"Round-trip mismatch:\n"
        f"  original:     {tool_args}\n"
        f"  deserialized: {deserialized}"
    )
