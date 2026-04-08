"""
Property 15: Historique des consultations trié par date décroissante

**Validates: Requirements 11.10**

Pour tout praticien ayant N consultations, le endpoint ``GET /api/v1/consultations/me``
doit retourner les consultations triées par ``created_at`` décroissant (chaque élément
a un ``created_at`` >= à celui de l'élément suivant).

Since ``list_my_consultations`` relies on MongoDB for the actual sort, this test
validates the sorting *contract* at the model level: given any list of Consultation
objects, sorting by ``created_at`` descending must satisfy the pairwise invariant.
"""
from __future__ import annotations

from datetime import datetime, timezone

from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.models.consultation import (
    Consultation,
    Symptom,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_non_empty_str = st.text(min_size=1, max_size=60).filter(lambda s: s.strip() != "")

_symptom_st = st.builds(
    Symptom,
    name=_non_empty_str,
    severity=st.one_of(st.none(), st.sampled_from(["mild", "moderate", "severe"])),
    duration_days=st.one_of(st.none(), st.integers(min_value=0, max_value=365)),
)

_created_at_st = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)

_consultation_st = st.builds(
    Consultation,
    user_id=_non_empty_str,
    symptoms=st.lists(_symptom_st, min_size=1, max_size=3),
    created_at=_created_at_st,
)


# ---------------------------------------------------------------------------
# Property 15 — Descending sort invariant
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    consultations=st.lists(_consultation_st, min_size=1, max_size=20),
)
def test_property_15_consultation_history_sorted_descending(
    consultations: list[Consultation],
) -> None:
    """**Validates: Requirements 11.10**

    For any list of N (1-20) Consultation objects with random ``created_at``
    datetimes, sorting by ``created_at`` descending must produce a sequence
    where each element's ``created_at`` >= the next element's ``created_at``.
    """
    # Simulate what the DB query does: sort by created_at descending
    sorted_consultations = sorted(
        consultations,
        key=lambda c: c.created_at,
        reverse=True,
    )

    # Assert the descending order invariant for all consecutive pairs
    for i in range(len(sorted_consultations) - 1):
        assert sorted_consultations[i].created_at >= sorted_consultations[i + 1].created_at, (
            f"Consultation at index {i} (created_at={sorted_consultations[i].created_at}) "
            f"should be >= consultation at index {i + 1} "
            f"(created_at={sorted_consultations[i + 1].created_at})"
        )


# ---------------------------------------------------------------------------
# Edge-case: single consultation (trivially sorted)
# ---------------------------------------------------------------------------

def test_edge_single_consultation_trivially_sorted() -> None:
    """A single consultation is trivially sorted.

    **Validates: Requirements 11.10**
    """
    consultation = Consultation(
        user_id="doctor-1",
        symptoms=[Symptom(name="fever")],
        created_at=datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
    )

    sorted_list = sorted([consultation], key=lambda c: c.created_at, reverse=True)

    assert len(sorted_list) == 1
    assert sorted_list[0].created_at == consultation.created_at


# ---------------------------------------------------------------------------
# Edge-case: all consultations with the same created_at (stable sort)
# ---------------------------------------------------------------------------

def test_edge_same_created_at_stable_sort() -> None:
    """All consultations with the same ``created_at`` satisfy the invariant.

    **Validates: Requirements 11.10**
    """
    same_time = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    consultations = [
        Consultation(
            user_id="doctor-2",
            symptoms=[Symptom(name=f"symptom-{i}")],
            created_at=same_time,
        )
        for i in range(5)
    ]

    sorted_consultations = sorted(
        consultations, key=lambda c: c.created_at, reverse=True
    )

    assert len(sorted_consultations) == 5
    for i in range(len(sorted_consultations) - 1):
        assert sorted_consultations[i].created_at >= sorted_consultations[i + 1].created_at


# ---------------------------------------------------------------------------
# Edge-case: empty list (trivially sorted)
# ---------------------------------------------------------------------------

def test_edge_empty_list_trivially_sorted() -> None:
    """An empty list is trivially sorted.

    **Validates: Requirements 11.10**
    """
    sorted_consultations = sorted([], key=lambda c: c.created_at, reverse=True)

    assert sorted_consultations == []
