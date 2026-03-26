"""Shared age-group computation utility."""
from __future__ import annotations

from datetime import date

from backend.models.common import AgeGroup


def compute_age_group(dob: date) -> AgeGroup:
    """Compute the clinical age group from a date of birth.

    Rules:
    - 0–28 days       → neonatal
    - 29 days–23 months → infant
    - 2–17 years      → child
    - 18 years and over → adult
    """
    today = date.today()
    delta_days = (today - dob).days

    if delta_days <= 28:
        return AgeGroup.NEONATAL

    # 29 days–23 months: less than 2 full years
    # Handle leap-day birthdays (Feb 29) in non-leap years → use Feb 28
    try:
        two_years_later = date(dob.year + 2, dob.month, dob.day)
    except ValueError:
        two_years_later = date(dob.year + 2, dob.month, 28)
    if today < two_years_later:
        return AgeGroup.INFANT

    # 2–17 years: less than 18 full years
    try:
        eighteen_years_later = date(dob.year + 18, dob.month, dob.day)
    except ValueError:
        eighteen_years_later = date(dob.year + 18, dob.month, 28)
    if today < eighteen_years_later:
        return AgeGroup.CHILD

    return AgeGroup.ADULT
