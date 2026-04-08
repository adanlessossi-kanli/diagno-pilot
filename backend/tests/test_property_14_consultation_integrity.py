"""
Property 14: Intégrité structurelle des Consultations MCP

**Validates: Requirements 11.2, 11.5, 11.6, 11.7, 11.8**

Pour toute session diagnostique MCP complétée, la Consultation créée doit contenir :
- user_id non-null et non vide
- mcp_session_id non-null et non vide
- agent_contributions (liste)
- evidence_citations (liste)
- symptoms (liste non vide)
- diagnoses (liste)
- created_at (datetime)
"""
from __future__ import annotations

from datetime import datetime, timezone

from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.models.consultation import (
    AgentContribution,
    Consultation,
    DifferentialDiagnosis,
    EvidenceCitation,
    Symptom,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_non_empty_str = st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != "")

_uuid_str = st.uuids().map(str)

_symptom_st = st.builds(
    Symptom,
    name=_non_empty_str,
    severity=st.one_of(st.none(), st.sampled_from(["mild", "moderate", "severe"])),
    duration_days=st.one_of(st.none(), st.integers(min_value=0, max_value=365)),
)

_diagnosis_st = st.builds(
    DifferentialDiagnosis,
    condition=_non_empty_str,
    probability=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    icd_code=st.one_of(
        st.none(),
        st.from_regex(r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$", fullmatch=True),
    ),
    matching_symptoms=st.lists(st.text(min_size=1, max_size=30), max_size=5),
)

_agent_contribution_st = st.builds(
    AgentContribution,
    agent_name=st.sampled_from(["epidemiology", "symptomatology", "lab", "treatment"]),
    confidence_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    partial_differential=st.just([]),
)

_evidence_citation_st = st.builds(
    EvidenceCitation,
    document_id=_uuid_str,
    title=_non_empty_str,
    source=_non_empty_str,
    excerpt=_non_empty_str,
    page=st.one_of(st.none(), st.integers(min_value=1, max_value=500)),
)

_created_at_st = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)


# ---------------------------------------------------------------------------
# Property 14 — Structural integrity of MCP Consultations
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    user_id=_non_empty_str,
    mcp_session_id=_uuid_str,
    symptoms=st.lists(_symptom_st, min_size=1, max_size=10),
    diagnoses=st.lists(_diagnosis_st, min_size=0, max_size=10),
    agent_contributions=st.lists(_agent_contribution_st, min_size=0, max_size=4),
    evidence_citations=st.lists(_evidence_citation_st, min_size=0, max_size=10),
    created_at=_created_at_st,
)
def test_property_14_mcp_consultation_structural_integrity(
    user_id: str,
    mcp_session_id: str,
    symptoms: list[Symptom],
    diagnoses: list[DifferentialDiagnosis],
    agent_contributions: list[AgentContribution],
    evidence_citations: list[EvidenceCitation],
    created_at: datetime,
) -> None:
    """**Validates: Requirements 11.2, 11.5, 11.6, 11.7, 11.8**

    For any completed MCP diagnostic session, the created Consultation must
    satisfy all structural invariants.
    """
    consultation = Consultation(
        user_id=user_id,
        symptoms=symptoms,
        diagnoses=diagnoses,
        created_at=created_at,
        mcp_session_id=mcp_session_id,
        agent_contributions=agent_contributions,
        evidence_citations=evidence_citations,
    )

    # user_id is not None and not empty (REQ 11.2)
    assert consultation.user_id is not None
    assert consultation.user_id.strip() != ""

    # mcp_session_id is not None and not empty (REQ 11.5)
    assert consultation.mcp_session_id is not None
    assert consultation.mcp_session_id.strip() != ""

    # agent_contributions is a list (REQ 11.6)
    assert isinstance(consultation.agent_contributions, list)

    # evidence_citations is a list (REQ 11.7)
    assert isinstance(consultation.evidence_citations, list)

    # symptoms is a non-empty list (REQ 11.8)
    assert isinstance(consultation.symptoms, list)
    assert len(consultation.symptoms) >= 1

    # diagnoses is a list (REQ 11.8)
    assert isinstance(consultation.diagnoses, list)

    # created_at is a datetime (REQ 11.8)
    assert isinstance(consultation.created_at, datetime)


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------

def test_edge_empty_agent_contributions_and_evidence_citations() -> None:
    """Consultation with empty agent_contributions and evidence_citations is valid.

    **Validates: Requirements 11.6, 11.7**
    """
    consultation = Consultation(
        user_id="doctor-123",
        symptoms=[Symptom(name="fever")],
        diagnoses=[],
        created_at=datetime.now(timezone.utc),
        mcp_session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        agent_contributions=[],
        evidence_citations=[],
    )

    assert consultation.agent_contributions == []
    assert consultation.evidence_citations == []
    assert isinstance(consultation.agent_contributions, list)
    assert isinstance(consultation.evidence_citations, list)


def test_edge_is_one_shot_true_when_patient_id_none() -> None:
    """Consultation with is_one_shot=True when patient_id is None.

    **Validates: Requirements 11.2, 11.5**
    """
    consultation = Consultation(
        patient_id=None,
        user_id="nurse-456",
        symptoms=[Symptom(name="headache", severity="moderate")],
        diagnoses=[
            DifferentialDiagnosis(condition="Migraine", probability=0.7),
        ],
        is_one_shot=True,
        created_at=datetime.now(timezone.utc),
        mcp_session_id="11111111-2222-3333-4444-555555555555",
        agent_contributions=[
            AgentContribution(
                agent_name="symptomatology",
                confidence_score=0.85,
                partial_differential=[],
            ),
        ],
        evidence_citations=[
            EvidenceCitation(
                document_id="doc-001",
                title="Migraine Guidelines",
                source="WHO",
                excerpt="Migraine is a common neurological disorder...",
                page=12,
            ),
        ],
    )

    assert consultation.patient_id is None
    assert consultation.is_one_shot is True
    assert consultation.user_id is not None
    assert consultation.mcp_session_id is not None
    assert len(consultation.symptoms) >= 1
    assert isinstance(consultation.created_at, datetime)
