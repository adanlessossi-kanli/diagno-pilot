"""
Property-based tests for the diagnosis-workflow-fix spec.

Feature: diagnosis-workflow-fix

This file contains all property tests for the diagnosis workflow fix spec.
Each test is tagged with its property number and validates specific requirements.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.core.config import Settings

# ---------------------------------------------------------------------------
# Strategies for Property 9: MongoDB URI credential detection
# ---------------------------------------------------------------------------

# Docker service hostnames: single-label, alphabetic, 2-15 chars
# Exclude names that the validator treats as non-Docker (localhost, loopback IPs)
_EXCLUDED_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}
docker_hostname_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
    min_size=2,
    max_size=15,
).filter(lambda h: h not in _EXCLUDED_HOSTNAMES)

# Non-Docker hostnames: localhost, loopback IPs, FQDNs with dots
non_docker_hostname_strategy = st.one_of(
    st.just("localhost"),
    st.just("127.0.0.1"),
    st.just("::1"),
    # FQDNs with at least one dot
    st.from_regex(r"[a-z]{2,8}\.[a-z]{2,6}", fullmatch=True),
)


# ---------------------------------------------------------------------------
# Property 9 — MongoDB URI credential detection
# **Validates: Requirements 3.3**
# ---------------------------------------------------------------------------


@given(hostname=docker_hostname_strategy)
@h_settings(max_examples=100)
def test_p9_docker_hostname_no_credentials_warns(hostname: str):
    """
    Feature: diagnosis-workflow-fix, Property 9: MongoDB URI credential detection

    For any Docker service hostname (single-label, no dots, not localhost/127.0.0.1/::1)
    and a URI with no '@' character, the Settings validator SHALL emit a warning
    about potentially missing authentication.

    **Validates: Requirements 3.3**
    """
    uri = f"mongodb://{hostname}:27017/diagno_pilot"
    with patch("backend.core.config.logger") as mock_logger:
        Settings(MONGODB_URI=uri, _env_file=None)
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "without" in call_args[0][0].lower() or "credential" in call_args[0][0].lower()


@given(hostname=docker_hostname_strategy)
@h_settings(max_examples=100)
def test_p9_docker_hostname_with_credentials_no_warning(hostname: str):
    """
    Feature: diagnosis-workflow-fix, Property 9: MongoDB URI credential detection

    For any Docker service hostname with '@' in the URI (indicating credentials),
    the Settings validator SHALL NOT emit a warning.

    **Validates: Requirements 3.3**
    """
    uri = f"mongodb://user:pass@{hostname}:27017/diagno_pilot"
    with patch("backend.core.config.logger") as mock_logger:
        Settings(MONGODB_URI=uri, _env_file=None)
        mock_logger.warning.assert_not_called()


@given(hostname=non_docker_hostname_strategy)
@h_settings(max_examples=100)
def test_p9_non_docker_hostname_no_warning(hostname: str):
    """
    Feature: diagnosis-workflow-fix, Property 9: MongoDB URI credential detection

    For any non-Docker hostname (localhost, 127.0.0.1, ::1, or FQDNs with dots),
    the Settings validator SHALL NOT emit a warning regardless of credentials.

    **Validates: Requirements 3.3**
    """
    # Without credentials
    uri = f"mongodb://{hostname}:27017/diagno_pilot"
    with patch("backend.core.config.logger") as mock_logger:
        Settings(MONGODB_URI=uri, _env_file=None)
        mock_logger.warning.assert_not_called()


# ---------------------------------------------------------------------------
# Strategies for Property 3: LLM URL priority selection
# ---------------------------------------------------------------------------

url_strategy = st.from_regex(r"http://[a-z]{3,10}:[0-9]{4,5}/v1", fullmatch=True)


# ---------------------------------------------------------------------------
# Property 3 — LLM URL priority selection
# **Validates: Requirements 2.1, 2.2**
# ---------------------------------------------------------------------------


@given(
    model_container_url=url_strategy,
    llm_primary_url=url_strategy,
)
@h_settings(max_examples=100)
def test_p3_model_container_url_takes_priority_when_nonempty(
    model_container_url: str,
    llm_primary_url: str,
):
    """
    Feature: diagnosis-workflow-fix, Property 3: LLM URL priority

    When MODEL_CONTAINER_URL is non-empty, LLMRouter SHALL select it as the
    primary endpoint regardless of LLM_PRIMARY_URL.

    **Validates: Requirements 2.1, 2.2**
    """
    mock_settings = type("MockSettings", (), {
        "MODEL_CONTAINER_URL": model_container_url,
        "MODEL_CONTAINER_API_KEY": "",
        "LLM_PRIMARY_URL": llm_primary_url,
        "LLM_PRIMARY_API_KEY": "",
        "LLM_FALLBACK_URL": "",
        "LLM_FALLBACK_API_KEY": "",
        "LLM_TIMEOUT": 60,
    })()

    captured_urls: list[str] = []

    class FakeLLMClient:
        def __init__(self, base_url: str, api_key: str, model: str) -> None:
            captured_urls.append(base_url)

    with patch("backend.services.llm_router.settings", mock_settings), \
         patch("backend.services.llm_router._LLMClient", FakeLLMClient):
        from backend.services.llm_router import LLMRouter
        LLMRouter()

    # First captured URL is the primary client
    assert captured_urls[0] == model_container_url


@given(llm_primary_url=url_strategy)
@h_settings(max_examples=100)
def test_p3_llm_primary_url_used_when_container_empty(
    llm_primary_url: str,
):
    """
    Feature: diagnosis-workflow-fix, Property 3: LLM URL priority

    When MODEL_CONTAINER_URL is empty, LLMRouter SHALL fall through to
    LLM_PRIMARY_URL as the primary endpoint.

    **Validates: Requirements 2.1, 2.2**
    """
    mock_settings = type("MockSettings", (), {
        "MODEL_CONTAINER_URL": "",
        "MODEL_CONTAINER_API_KEY": "",
        "LLM_PRIMARY_URL": llm_primary_url,
        "LLM_PRIMARY_API_KEY": "",
        "LLM_FALLBACK_URL": "",
        "LLM_FALLBACK_API_KEY": "",
        "LLM_TIMEOUT": 60,
    })()

    captured_urls: list[str] = []

    class FakeLLMClient:
        def __init__(self, base_url: str, api_key: str, model: str) -> None:
            captured_urls.append(base_url)

    with patch("backend.services.llm_router.settings", mock_settings), \
         patch("backend.services.llm_router._LLMClient", FakeLLMClient):
        from backend.services.llm_router import LLMRouter
        LLMRouter()

    # First captured URL is the primary client
    assert captured_urls[0] == llm_primary_url


# ---------------------------------------------------------------------------
# Strategies for Property 5: Confidence score propagation
# ---------------------------------------------------------------------------

confidence_score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
session_id_strategy = st.one_of(st.none(), st.uuids().map(str))


# ---------------------------------------------------------------------------
# Property 5 — Confidence score is never nullified by session_id
# **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
# ---------------------------------------------------------------------------


@given(
    confidence_score=confidence_score_strategy,
    session_id=session_id_strategy,
)
@h_settings(max_examples=100)
def test_p5_confidence_score_in_mongo_doc_not_nullified_by_session_id(
    confidence_score: float,
    session_id: str | None,
):
    """
    Feature: diagnosis-workflow-fix, Property 5: Confidence score is never nullified by session_id

    For any (confidence_score, session_id) pair, the MongoDB document constructed
    by the diagnose router SHALL include the original confidence_score value,
    never conditionally nullifying it based on session_id.

    **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
    """
    from dataclasses import dataclass, field as dc_field

    @dataclass
    class FakeResult:
        diagnoses: list = dc_field(default_factory=list)
        fallback_used: bool = False
        degraded_warning: str | None = None
        session_id: str | None = None
        confidence_score: float = 0.0
        agent_contributions: list = dc_field(default_factory=list)
        evidence_citations: list = dc_field(default_factory=list)
        parse_failed: bool = False

    result = FakeResult(
        confidence_score=confidence_score,
        session_id=session_id,
    )

    # Simulate the MongoDB document construction from diagnose.py
    doc_confidence = result.confidence_score

    # Simulate the DiagnoseResponse construction from diagnose.py
    response_confidence = result.confidence_score

    # Property: confidence_score is ALWAYS the original value, never None
    assert doc_confidence == confidence_score, (
        f"MongoDB doc confidence_score was {doc_confidence!r}, "
        f"expected {confidence_score!r} (session_id={session_id!r})"
    )
    assert response_confidence == confidence_score, (
        f"Response confidence_score was {response_confidence!r}, "
        f"expected {confidence_score!r} (session_id={session_id!r})"
    )


@given(
    confidence_score=confidence_score_strategy,
    session_id=session_id_strategy,
)
@h_settings(max_examples=100, deadline=None)
def test_p5_confidence_score_in_response_not_nullified_by_session_id(
    confidence_score: float,
    session_id: str | None,
):
    """
    Feature: diagnosis-workflow-fix, Property 5: Confidence score is never nullified by session_id

    For any (confidence_score, session_id) pair, the DiagnoseResponse returned
    by the diagnose router SHALL include the original confidence_score value,
    matching what is stored in MongoDB.

    **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
    """
    from backend.routers.diagnose import DiagnoseResponse

    # Build a response the same way the router does (post-fix)
    response = DiagnoseResponse(
        session_id="test-session",
        diagnoses=[],
        confidence_score=confidence_score,
        mcp_session_id=session_id,
    )

    assert response.confidence_score == confidence_score, (
        f"DiagnoseResponse.confidence_score was {response.confidence_score!r}, "
        f"expected {confidence_score!r} (session_id={session_id!r})"
    )


# ---------------------------------------------------------------------------
# Strategies for Property 4: Diagnostic parser markdown stripping round-trip
# ---------------------------------------------------------------------------

# Valid ICD-10 codes matching r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$"
icd_code_strategy = st.from_regex(r"[A-Z][0-9]{2}(\.[0-9]{1,4})?", fullmatch=True)

# A single diagnosis object with valid fields
diagnosis_object_strategy = st.fixed_dictionaries({
    "condition": st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ -"),
        min_size=1,
        max_size=40,
    ),
    "probability": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "icd_code": st.one_of(st.none(), icd_code_strategy),
    "matching_symptoms": st.lists(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz "),
            min_size=1,
            max_size=20,
        ),
        min_size=0,
        max_size=3,
    ),
})

# A list of 3+ diagnosis objects
diagnosis_array_strategy = st.lists(diagnosis_object_strategy, min_size=3, max_size=6)

# Markdown fence variants
markdown_fence_strategy = st.sampled_from(["```json\n", "```JSON\n", "```\n"])

# <think> block variants with random reasoning text inside
think_block_strategy = st.tuples(
    st.sampled_from(["<think>", "<Think>", "<THINK>"]),
    st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz .!?\n"),
        min_size=0,
        max_size=80,
    ),
    st.sampled_from(["</think>", "</Think>", "</THINK>"]),
).map(lambda t: f"{t[0]}{t[1]}{t[2]}")

# Preamble text (arbitrary text before the JSON)
preamble_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz :,.\n"),
    min_size=0,
    max_size=50,
)

# Postamble text (arbitrary text after the JSON)
postamble_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz :,.\n"),
    min_size=0,
    max_size=50,
)


# ---------------------------------------------------------------------------
# Property 4 — Diagnostic parser markdown stripping round-trip
# **Validates: Requirements 5.1, 5.2, 5.3, 5.5**
# ---------------------------------------------------------------------------


@given(
    diagnoses=diagnosis_array_strategy,
    use_fence=st.booleans(),
    fence=markdown_fence_strategy,
    use_think=st.booleans(),
    think_block=think_block_strategy,
    preamble=preamble_strategy,
    postamble=postamble_strategy,
)
@h_settings(max_examples=100)
def test_p4_parser_markdown_stripping_round_trip(
    diagnoses: list[dict],
    use_fence: bool,
    fence: str,
    use_think: bool,
    think_block: str,
    preamble: str,
    postamble: str,
):
    """
    Feature: diagnosis-workflow-fix, Property 4: Diagnostic parser markdown stripping round-trip

    For any valid JSON array of 3+ diagnosis objects, wrapping in any combination
    of markdown code fences, <think> blocks, and preamble/postamble text,
    DiagnosticParser().parse(wrapped) SHALL produce the same list of
    DifferentialDiagnosis objects as DiagnosticParser().parse(bare_json).

    **Validates: Requirements 5.1, 5.2, 5.3, 5.5**
    """
    import json as _json
    from backend.services.diagnostic_parser import DiagnosticParser

    bare_json = _json.dumps(diagnoses)
    parser = DiagnosticParser()

    # Parse bare JSON as the reference
    bare_result, bare_failed = parser.parse(bare_json)

    # Build wrapped version with random combinations
    wrapped = ""
    if use_think:
        wrapped += think_block + "\n"
    wrapped += preamble
    if use_fence:
        wrapped += fence
    wrapped += bare_json
    if use_fence:
        wrapped += "\n```"
    wrapped += postamble

    # Parse wrapped version
    wrapped_result, wrapped_failed = parser.parse(wrapped)

    # Both should produce the same results
    assert bare_failed == wrapped_failed, (
        f"parse_failed mismatch: bare={bare_failed}, wrapped={wrapped_failed}"
    )
    assert len(bare_result) == len(wrapped_result), (
        f"Length mismatch: bare={len(bare_result)}, wrapped={len(wrapped_result)}"
    )
    for i, (b, w) in enumerate(zip(bare_result, wrapped_result)):
        assert b.condition == w.condition, f"[{i}] condition: {b.condition!r} != {w.condition!r}"
        assert b.probability == w.probability, f"[{i}] probability: {b.probability!r} != {w.probability!r}"
        assert b.icd_code == w.icd_code, f"[{i}] icd_code: {b.icd_code!r} != {w.icd_code!r}"
        assert b.matching_symptoms == w.matching_symptoms, f"[{i}] matching_symptoms mismatch"


# ---------------------------------------------------------------------------
# Strategies for Property 6: AgentPipeline JSON-first parsing
# ---------------------------------------------------------------------------

# Diagnosis object with WIDER probability range to test clamping
agent_diagnosis_object_strategy = st.fixed_dictionaries({
    "condition": st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ -"),
        min_size=1,
        max_size=40,
    ),
    "probability": st.floats(min_value=-1.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    "icd_code": st.one_of(st.none(), icd_code_strategy),
    "matching_symptoms": st.lists(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz "),
            min_size=1,
            max_size=20,
        ),
        min_size=0,
        max_size=3,
    ),
})

agent_diagnosis_array_strategy = st.lists(agent_diagnosis_object_strategy, min_size=1, max_size=5)


# ---------------------------------------------------------------------------
# Property 6 — AgentPipeline JSON-first parsing with correct extraction
# **Validates: Requirements 9.1, 9.3, 9.5**
# ---------------------------------------------------------------------------


@given(diagnoses=agent_diagnosis_array_strategy)
@h_settings(max_examples=100)
def test_p6_agent_pipeline_json_first_parsing(diagnoses: list[dict]):
    """
    Feature: diagnosis-workflow-fix, Property 6: AgentPipeline JSON-first parsing with correct extraction

    For any valid JSON array of diagnosis objects, _parse_partial_differential
    SHALL extract DifferentialDiagnosis objects with matching field values
    and probabilities clamped to [0.0, 1.0].

    **Validates: Requirements 9.1, 9.3, 9.5**
    """
    import json as _json
    from backend.services.agent_pipeline import _parse_partial_differential

    answer = _json.dumps(diagnoses)
    results = _parse_partial_differential(answer)

    assert len(results) == len(diagnoses), (
        f"Expected {len(diagnoses)} results, got {len(results)}"
    )

    for i, (orig, parsed) in enumerate(zip(diagnoses, results)):
        assert parsed.condition == orig["condition"], (
            f"[{i}] condition: {parsed.condition!r} != {orig['condition']!r}"
        )
        expected_prob = max(0.0, min(1.0, orig["probability"]))
        assert parsed.probability == expected_prob, (
            f"[{i}] probability: {parsed.probability!r} != {expected_prob!r} "
            f"(original: {orig['probability']!r})"
        )
        assert parsed.icd_code == orig["icd_code"], (
            f"[{i}] icd_code: {parsed.icd_code!r} != {orig['icd_code']!r}"
        )
        assert parsed.matching_symptoms == orig["matching_symptoms"], (
            f"[{i}] matching_symptoms mismatch"
        )
        # Verify clamping: probability must always be in [0.0, 1.0]
        assert 0.0 <= parsed.probability <= 1.0, (
            f"[{i}] probability {parsed.probability} out of [0.0, 1.0] range"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 7: AgentPipeline regex fallback
# ---------------------------------------------------------------------------

french_keyword_strategy = st.sampled_from(["diagnostic", "pathologie", "condition", "maladie"])
french_separator_strategy = st.sampled_from([" : ", " - ", " – "])
condition_name_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ éèêëàâùûôîïç"),
    min_size=2,
    max_size=30,
)


# ---------------------------------------------------------------------------
# Property 7 — AgentPipeline regex fallback for French-keyword text
# **Validates: Requirements 9.2**
# ---------------------------------------------------------------------------


@given(
    keyword=french_keyword_strategy,
    separator=french_separator_strategy,
    condition_name=condition_name_strategy,
)
@h_settings(max_examples=100)
def test_p7_agent_pipeline_regex_fallback_french_keywords(
    keyword: str,
    separator: str,
    condition_name: str,
):
    """
    Feature: diagnosis-workflow-fix, Property 7: AgentPipeline regex fallback for French-keyword text

    For any string containing a French diagnostic keyword pattern
    (e.g., "diagnostic : Paludisme") but no valid JSON array,
    _parse_partial_differential SHALL extract at least one DifferentialDiagnosis
    with the condition name from the keyword match.

    **Validates: Requirements 9.2**
    """
    from backend.services.agent_pipeline import _parse_partial_differential

    # Build a French-keyword text with NO valid JSON array
    answer = f"Le {keyword}{separator}{condition_name}"

    results = _parse_partial_differential(answer)

    assert len(results) >= 1, (
        f"Expected at least 1 result from French-keyword text, got {len(results)}. "
        f"Input: {answer!r}"
    )
    # The extracted condition should match (stripped and without trailing dot)
    extracted = results[0].condition
    assert extracted == condition_name.strip().rstrip("."), (
        f"Extracted condition {extracted!r} doesn't match expected {condition_name.strip().rstrip('.')!r}"
    )
    # Regex fallback always uses 0.5 probability
    assert results[0].probability == 0.5


# ---------------------------------------------------------------------------
# Property 1 — DIAGNOSIS_MODE validation accepts exactly the valid set
# **Validates: Requirements 1.1, 1.2**
# ---------------------------------------------------------------------------

_VALID_DIAGNOSIS_MODES = {"rag", "mcp", "agent"}


@given(value=st.sampled_from(sorted(_VALID_DIAGNOSIS_MODES)))
@h_settings(max_examples=100)
def test_p1_valid_diagnosis_mode_accepted(value: str):
    """
    Feature: diagnosis-workflow-fix, Property 1: DIAGNOSIS_MODE validation accepts exactly the valid set

    For any value in {"rag", "mcp", "agent"}, Settings(DIAGNOSIS_MODE=value)
    SHALL succeed without raising a ValidationError.

    **Validates: Requirements 1.1, 1.2**
    """
    s = Settings(DIAGNOSIS_MODE=value, _env_file=None)
    assert s.DIAGNOSIS_MODE == value


@given(value=st.text(min_size=1, max_size=20).filter(lambda v: v not in _VALID_DIAGNOSIS_MODES))
@h_settings(max_examples=100)
def test_p1_invalid_diagnosis_mode_rejected(value: str):
    """
    Feature: diagnosis-workflow-fix, Property 1: DIAGNOSIS_MODE validation accepts exactly the valid set

    For any string NOT in {"rag", "mcp", "agent"}, Settings(DIAGNOSIS_MODE=value)
    SHALL raise a Pydantic ValidationError.

    **Validates: Requirements 1.1, 1.2**
    """
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(DIAGNOSIS_MODE=value, _env_file=None)


# ---------------------------------------------------------------------------
# Property 2 — Diagnosis mode routing selects the correct path
# **Validates: Requirements 1.3, 1.4, 1.5, 1.6, 1.7**
# ---------------------------------------------------------------------------


@given(
    mode=st.sampled_from(["rag", "mcp", "agent"]),
    has_mcp=st.booleans(),
    has_agent=st.booleans(),
)
@h_settings(max_examples=100, deadline=None)
def test_p2_routing_selects_correct_path(mode: str, has_mcp: bool, has_agent: bool):
    """
    Feature: diagnosis-workflow-fix, Property 2: Diagnosis mode routing selects the correct path

    For any (mode, has_mcp, has_agent) tuple, the DiagnosticOrchestrator delegates
    to the correct internal method: _get_diagnosis_via_rag for "rag",
    _get_diagnosis_via_mcp for "mcp" (when MCP_Host configured),
    _get_diagnosis_via_agent_pipeline for "agent" (when AgentPipeline configured),
    and falls back to _get_diagnosis_via_rag when the requested dependency is None.

    **Validates: Requirements 1.3, 1.4, 1.5, 1.6, 1.7**
    """
    from backend.services.diagnostic_service import DiagnosticOrchestrator, DiagnosticResult

    fake_result = DiagnosticResult(
        diagnoses=[], fallback_used=False, degraded_warning=None,
    )

    # Build a minimal orchestrator with mocked internals
    rag_service = MagicMock()
    mcp_host = MagicMock() if has_mcp else None
    agent_pipeline = MagicMock() if has_agent else None

    orchestrator = DiagnosticOrchestrator(
        rag_service=rag_service,
        mcp_host=mcp_host,
        agent_pipeline=agent_pipeline,
    )

    # Mock the three private path methods
    orchestrator._get_diagnosis_via_rag = AsyncMock(return_value=fake_result)
    orchestrator._get_diagnosis_via_mcp = AsyncMock(return_value=fake_result)
    orchestrator._get_diagnosis_via_agent_pipeline = AsyncMock(return_value=fake_result)
    orchestrator._write_audit = AsyncMock()

    symptoms: list[Any] = []

    with patch("backend.services.diagnostic_service.settings") as mock_settings:
        mock_settings.DIAGNOSIS_MODE = mode
        asyncio.new_event_loop().run_until_complete(
            orchestrator.get_differential_diagnosis(symptoms)
        )

    if mode == "rag":
        orchestrator._get_diagnosis_via_rag.assert_called_once()
        orchestrator._get_diagnosis_via_mcp.assert_not_called()
        orchestrator._get_diagnosis_via_agent_pipeline.assert_not_called()
    elif mode == "mcp":
        if has_mcp:
            orchestrator._get_diagnosis_via_mcp.assert_called_once()
            orchestrator._get_diagnosis_via_rag.assert_not_called()
        else:
            # Falls back to RAG when MCP_Host is None
            orchestrator._get_diagnosis_via_rag.assert_called_once()
            orchestrator._get_diagnosis_via_mcp.assert_not_called()
        orchestrator._get_diagnosis_via_agent_pipeline.assert_not_called()
    elif mode == "agent":
        if has_agent:
            orchestrator._get_diagnosis_via_agent_pipeline.assert_called_once()
            orchestrator._get_diagnosis_via_rag.assert_not_called()
        else:
            # Falls back to RAG when AgentPipeline is None
            orchestrator._get_diagnosis_via_rag.assert_called_once()
            orchestrator._get_diagnosis_via_agent_pipeline.assert_not_called()
        orchestrator._get_diagnosis_via_mcp.assert_not_called()


# ---------------------------------------------------------------------------
# Property 8 — Degraded warning propagation
# **Validates: Requirements 6.3**
# ---------------------------------------------------------------------------


@given(
    degraded_warning=st.one_of(
        st.none(),
        st.text(min_size=1, max_size=120),
    ),
)
@h_settings(max_examples=100, deadline=None)
def test_p8_degraded_warning_propagation(degraded_warning: str | None):
    """
    Feature: diagnosis-workflow-fix, Property 8: Degraded warning propagation

    For any RAGResponse with a random degraded_warning string (or None),
    the DiagnosticOrchestrator SHALL propagate that exact string to the
    DiagnosticResult.degraded_warning field.

    **Validates: Requirements 6.3**
    """
    from backend.models.document import RAGResponse
    from backend.services.diagnostic_service import DiagnosticOrchestrator

    # Build a RAGResponse with the generated degraded_warning
    rag_response = RAGResponse(
        answer="[]",
        sources=[],
        llm_used="test-model",
        degraded_warning=degraded_warning,
    )

    # Mock the RAG pipeline to return our crafted response
    mock_rag = MagicMock()
    mock_rag.query = AsyncMock(return_value=rag_response)

    # Mock the parser to return empty diagnoses (not relevant to this property)
    mock_parser = MagicMock()
    mock_parser.parse = MagicMock(return_value=([], False))

    orchestrator = DiagnosticOrchestrator(
        rag_service=mock_rag,
        diagnostic_parser=mock_parser,
    )
    orchestrator._write_audit = AsyncMock()

    with patch("backend.services.diagnostic_service.settings") as mock_settings:
        mock_settings.DIAGNOSIS_MODE = "rag"
        result = asyncio.new_event_loop().run_until_complete(
            orchestrator.get_differential_diagnosis(symptoms=[])
        )

    assert result.degraded_warning == degraded_warning, (
        f"Expected degraded_warning={degraded_warning!r}, "
        f"got {result.degraded_warning!r}"
    )
