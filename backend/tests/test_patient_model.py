"""
Property-based tests for PatientProfile age_group computation.

Feature: diagno-pilot-improvements
"""

from datetime import date, timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.models.common import AgeGroup
from backend.models.patient import PatientProfile, _compute_age_group

# ---------------------------------------------------------------------------
# Hypothesis profile
# ---------------------------------------------------------------------------

settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ci")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expected_age_group(dob: date) -> AgeGroup:
    """Mirror of _compute_age_group — used to cross-check in tests."""
    today = date.today()
    delta_days = (today - dob).days

    if delta_days <= 28:
        return AgeGroup.NEONATAL

    try:
        two_years_later = date(dob.year + 2, dob.month, dob.day)
    except ValueError:
        two_years_later = date(dob.year + 2, dob.month, 28)
    if today < two_years_later:
        return AgeGroup.INFANT

    try:
        eighteen_years_later = date(dob.year + 18, dob.month, dob.day)
    except ValueError:
        eighteen_years_later = date(dob.year + 18, dob.month, 28)
    if today < eighteen_years_later:
        return AgeGroup.CHILD

    return AgeGroup.ADULT


def _make_profile(dob: date, **kwargs) -> PatientProfile:
    return PatientProfile(full_name="Test Patient", date_of_birth=dob, **kwargs)


# ---------------------------------------------------------------------------
# P16 — Calcul automatique de age_group depuis date_of_birth
# Feature: diagno-pilot-improvements, Property 16: Calcul automatique de age_group depuis date_of_birth
# Validates: Requirements 13.1
# ---------------------------------------------------------------------------

@given(dob=st.dates(min_value=date(1900, 1, 1), max_value=date.today()))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_p16_age_group_computed_from_dob(dob: date) -> None:
    """
    Property 16: For any valid date of birth, creating a PatientProfile must
    produce an age_group matching exactly the classification rules.

    Validates: Requirements 13.1
    """
    profile = _make_profile(dob)
    expected = _expected_age_group(dob)
    assert profile.age_group == expected, (
        f"dob={dob}, delta_days={(date.today() - dob).days}, "
        f"expected={expected}, got={profile.age_group}"
    )


def test_p16_boundary_day_0() -> None:
    """Boundary: born today (day 0) → neonatal."""
    dob = date.today()
    profile = _make_profile(dob)
    assert profile.age_group == AgeGroup.NEONATAL


def test_p16_boundary_day_28() -> None:
    """Boundary: born 28 days ago → neonatal (last day)."""
    dob = date.today() - timedelta(days=28)
    profile = _make_profile(dob)
    assert profile.age_group == AgeGroup.NEONATAL


def test_p16_boundary_day_29() -> None:
    """Boundary: born 29 days ago → infant (first day)."""
    dob = date.today() - timedelta(days=29)
    profile = _make_profile(dob)
    assert profile.age_group == AgeGroup.INFANT


def test_p16_boundary_exactly_2_years() -> None:
    """Boundary: exactly 2 years old today → child (first day)."""
    today = date.today()
    dob = date(today.year - 2, today.month, today.day)
    profile = _make_profile(dob)
    assert profile.age_group == AgeGroup.CHILD


def test_p16_boundary_one_day_before_2_years() -> None:
    """Boundary: one day before 2 years → infant (last day)."""
    today = date.today()
    two_years_birthday = date(today.year - 2, today.month, today.day)
    dob = two_years_birthday + timedelta(days=1)
    profile = _make_profile(dob)
    assert profile.age_group == AgeGroup.INFANT


def test_p16_boundary_exactly_18_years() -> None:
    """Boundary: exactly 18 years old today → adult (first day)."""
    today = date.today()
    dob = date(today.year - 18, today.month, today.day)
    profile = _make_profile(dob)
    assert profile.age_group == AgeGroup.ADULT


def test_p16_boundary_one_day_before_18_years() -> None:
    """Boundary: one day before 18 years → child (last day)."""
    today = date.today()
    eighteen_years_birthday = date(today.year - 18, today.month, today.day)
    dob = eighteen_years_birthday + timedelta(days=1)
    profile = _make_profile(dob)
    assert profile.age_group == AgeGroup.CHILD


# ---------------------------------------------------------------------------
# P17 — Idempotence du calcul de age_group
# Feature: diagno-pilot-improvements, Property 17: Idempotence du calcul de age_group
# Validates: Requirements 13.5
# ---------------------------------------------------------------------------

@given(dob=st.dates(min_value=date(1900, 1, 1), max_value=date.today()))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_p17_age_group_idempotent(dob: date) -> None:
    """
    Property 17: Calling _compute_age_group(dob) twice must return the same
    result (idempotence).

    Validates: Requirements 13.5
    """
    first = _compute_age_group(dob)
    second = _compute_age_group(dob)
    assert first == second, (
        f"dob={dob}: first call returned {first}, second call returned {second}"
    )


@given(
    dob=st.dates(min_value=date(1900, 1, 1), max_value=date.today()),
    explicit_age_group=st.sampled_from(list(AgeGroup)),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_p17_explicit_age_group_overridden_by_dob(
    dob: date, explicit_age_group: AgeGroup
) -> None:
    """
    Property 17 (corollary): Creating a PatientProfile with date_of_birth and
    any explicit age_group value must always produce the computed value, not
    the explicit one.

    Validates: Requirements 13.5
    """
    profile = _make_profile(dob, age_group=explicit_age_group)
    expected = _compute_age_group(dob)
    assert profile.age_group == expected, (
        f"dob={dob}, explicit={explicit_age_group}, "
        f"expected computed={expected}, got={profile.age_group}"
    )
