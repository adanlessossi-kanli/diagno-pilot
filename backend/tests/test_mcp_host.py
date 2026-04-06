"""
Tests for MCP_Host — Diagno-Pilot
Feature: diagno-pilot-improvements, Property 5: source_filter correct pour chaque agent spécialiste
Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.models.consultation import Symptom
from backend.services.mcp_host import SOURCE_FILTERS, MCP_Host


# ---------------------------------------------------------------------------
# Expected source filters per agent (REQ 2.3, 2.4, 2.5, 2.6)
# ---------------------------------------------------------------------------

EXPECTED_SOURCE_FILTERS: dict[str, dict] = {
    "epidemiology": {"metadata.document_type": "epidemiology"},
    "symptomatology": {"metadata.document_type": "guideline"},
    "lab": {"metadata.document_type": "laboratory"},
    "treatment": {"metadata.document_type": {"$in": ["protocol", "guideline"]}},
}


# ---------------------------------------------------------------------------
# Unit tests — SOURCE_FILTERS correctness
# ---------------------------------------------------------------------------


class TestSourceFiltersDict:
    """Verify that SOURCE_FILTERS contains the correct values for all 4 agents."""

    def test_source_filters_has_all_four_agents(self):
        """SOURCE_FILTERS must define entries for all four specialist agents."""
        assert set(SOURCE_FILTERS.keys()) == {"epidemiology", "symptomatology", "lab", "treatment"}

    def test_epidemiology_filter(self):
        """Epidemiology agent must filter on document_type == 'epidemiology'."""
        assert SOURCE_FILTERS["epidemiology"] == {"metadata.document_type": "epidemiology"}

    def test_symptomatology_filter(self):
        """Symptomatology agent must filter on document_type == 'guideline'."""
        assert SOURCE_FILTERS["symptomatology"] == {"metadata.document_type": "guideline"}

    def test_lab_filter(self):
        """Lab agent must filter on document_type == 'laboratory'."""
        assert SOURCE_FILTERS["lab"] == {"metadata.document_type": "laboratory"}

    def test_treatment_filter(self):
        """Treatment agent must filter on document_type in ['protocol', 'guideline']."""
        assert SOURCE_FILTERS["treatment"] == {
            "metadata.document_type": {"$in": ["protocol", "guideline"]}
        }

    def test_source_filters_match_expected(self):
        """SOURCE_FILTERS must exactly match the expected mapping for all agents."""
        assert SOURCE_FILTERS == EXPECTED_SOURCE_FILTERS


# ---------------------------------------------------------------------------
# Helpers for property-based test
# ---------------------------------------------------------------------------


def _make_symptom(name: str) -> Symptom:
    return Symptom(name=name)


def _make_mock_process(payload: dict) -> MagicMock:
    """Return a mock asyncio subprocess that echoes a valid agent response."""
    stdout_bytes = json.dumps(payload).encode()
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(stdout_bytes, b""))
    mock_proc.kill = MagicMock()
    return mock_proc


# ---------------------------------------------------------------------------
# Property-based test P5
# ---------------------------------------------------------------------------

# Hypothesis strategy: list of 1–10 non-empty symptom names
_symptom_names_strategy = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters=" -"),
        min_size=1,
        max_size=30,
    ).filter(lambda s: s.strip()),
    min_size=1,
    max_size=10,
)


# Feature: diagno-pilot-improvements, Property 5: source_filter correct pour chaque agent spécialiste
@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(symptom_names=_symptom_names_strategy)
async def test_property_5_source_filter_correct_per_agent(symptom_names: list[str]):
    """Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6

    For any list of symptoms, when MCP_Host.run_diagnostic() is called, each
    specialist agent must receive the correct source_filter in its JSON request
    payload sent via stdin.
    """
    symptoms = [_make_symptom(name) for name in symptom_names]

    # Capture the stdin payloads sent to each agent subprocess
    captured_payloads: dict[str, dict] = {}

    # Valid agent response stub
    agent_response = json.dumps(
        {"chunks": [], "confidence_score": 0.0, "partial_differential": []}
    ).encode()

    async def fake_create_subprocess_exec(*args, **kwargs):
        """Intercept subprocess creation, capture stdin payload on communicate()."""
        # Identify agent by script path (second positional arg after "python")
        script_path: str = args[1] if len(args) > 1 else ""
        agent_name = script_path.split("/")[-1].replace("_agent.py", "")

        mock_proc = MagicMock()

        async def fake_communicate(input: bytes | None = None):  # noqa: A002
            if input is not None:
                try:
                    captured_payloads[agent_name] = json.loads(input.decode())
                except Exception:
                    pass
            return (agent_response, b"")

        mock_proc.communicate = fake_communicate
        mock_proc.kill = MagicMock()
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
        host = MCP_Host()
        results, audit = await host.run_diagnostic(
            symptoms=symptoms,
            patient_profile=None,
            locale="fr-TG",
            region=None,
        )

    # All four agents must have been called
    assert set(captured_payloads.keys()) == {"epidemiology", "symptomatology", "lab", "treatment"}, (
        f"Expected all 4 agents to be called, got: {set(captured_payloads.keys())}"
    )

    # Each agent must have received the correct source_filter
    for agent_name, expected_filter in EXPECTED_SOURCE_FILTERS.items():
        payload = captured_payloads[agent_name]
        assert "source_filter" in payload, (
            f"Agent '{agent_name}' payload missing 'source_filter' key"
        )
        assert payload["source_filter"] == expected_filter, (
            f"Agent '{agent_name}' received wrong source_filter: "
            f"got {payload['source_filter']!r}, expected {expected_filter!r}"
        )
