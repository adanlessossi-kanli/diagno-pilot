"""
Tests de propriété pour le calcul du groupe d'âge — Diagno-Pilot

**Validates: Requirements REQ-06, REQ-08**

Propriété 3 : Pour tout `date_of_birth` valide, le groupe d'âge calculé
correspond exactement aux tranches définies :
  - néonatal  : 0–28 jours
  - nourrisson : 1–23 mois (29 jours – 23 mois révolus)
  - enfant    : 2–17 ans
  - adulte    : 18+ ans
"""
from __future__ import annotations

from datetime import date

from hypothesis import assume, given, settings as h_settings
from hypothesis import strategies as st

from backend.models.common import AgeGroup
from backend.services.patient_service import _compute_age_group

# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

# Generate any calendar date; future dates are filtered out with assume().
date_strategy = st.dates(
    min_value=date(1900, 1, 1),
    max_value=date(2100, 12, 31),
)


# ---------------------------------------------------------------------------
# Helper — replicate the boundary logic from _compute_age_group
# ---------------------------------------------------------------------------

def _expected_age_group(dob: date) -> AgeGroup:
    today = date.today()
    days_old = (today - dob).days

    if days_old <= 28:
        return AgeGroup.NEONATAL

    months_old = (today.year - dob.year) * 12 + (today.month - dob.month)
    if months_old < 24:
        return AgeGroup.INFANT

    years_old = today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )
    if years_old < 18:
        return AgeGroup.CHILD

    return AgeGroup.ADULT


# ---------------------------------------------------------------------------
# Property 3 : age group boundaries are respected for every valid date of birth
# ---------------------------------------------------------------------------

@given(dob=date_strategy)
@h_settings(max_examples=500)
def test_age_group_matches_defined_boundaries(dob: date):
    """
    **Validates: Requirements REQ-06, REQ-08**

    For any valid date of birth (not in the future), `_compute_age_group`
    must return the AgeGroup that exactly matches the defined age brackets:
      - NEONATAL  : days_old <= 28
      - INFANT    : days_old > 28 AND months_old < 24
      - CHILD     : months_old >= 24 AND years_old < 18
      - ADULT     : years_old >= 18
    """
    today = date.today()

    # Filter out future dates — a patient cannot be born in the future.
    assume(dob <= today)

    result = _compute_age_group(dob)
    expected = _expected_age_group(dob)

    assert result == expected, (
        f"dob={dob}: expected {expected.value!r}, got {result.value!r} "
        f"(days_old={(today - dob).days})"
    )
