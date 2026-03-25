"""
Tests de propriété pour la configuration CORS — Diagno-Pilot

Feature: diagno-pilot-improvements

Property 1 : Configuration CORS invalide en production lève une erreur
**Validates: Requirements 1.1, 1.4**

Property 2 : Round-trip parsing des origines CORS
**Validates: Requirements 1.2**
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.core.config import Settings

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Invalid ALLOWED_ORIGINS values for production: wildcard or blank-ish strings
invalid_origins_strategy = st.one_of(
    st.just("*"),
    st.just(""),
    st.just("  "),
    st.just(" * "),
)

# Valid URL origins (simplified but realistic)
valid_origin_strategy = st.from_regex(
    r"https?://[a-z]{3,10}(\.[a-z]{2,6}){1,2}(:[0-9]{2,5})?",
    fullmatch=True,
)

# A list of 1–5 valid origins
valid_origins_list_strategy = st.lists(valid_origin_strategy, min_size=1, max_size=5)


# ---------------------------------------------------------------------------
# Property 1 — CORS config invalide en production lève une erreur
# ---------------------------------------------------------------------------

@given(invalid_origins=invalid_origins_strategy)
@h_settings(max_examples=50)
def test_p1_invalid_cors_in_production_raises(invalid_origins: str):
    """
    Feature: diagno-pilot-improvements, Property 1:
    Pour toute combinaison ENV=production + ALLOWED_ORIGINS invalide (* ou vide),
    l'instanciation de Settings doit lever une ValidationError.
    """
    with pytest.raises((ValidationError, ValueError)):
        Settings(
            ENV="production",
            ALLOWED_ORIGINS=invalid_origins,
            # Provide required-ish fields with defaults to isolate CORS validation
            JWT_SECRET="test_secret_long_enough",
        )


def test_p1_valid_cors_in_production_does_not_raise():
    """Sanity check: explicit origins in production must not raise."""
    s = Settings(
        ENV="production",
        ALLOWED_ORIGINS="https://app.example.com,https://api.example.com",
        JWT_SECRET="test_secret_long_enough",
    )
    assert s.ENV == "production"


def test_p1_wildcard_in_development_does_not_raise():
    """Wildcard is acceptable outside production."""
    s = Settings(ENV="development", ALLOWED_ORIGINS="*")
    assert s.ALLOWED_ORIGINS == "*"


# ---------------------------------------------------------------------------
# Property 2 — Round-trip parsing des origines CORS
# ---------------------------------------------------------------------------

@given(origins=valid_origins_list_strategy)
@h_settings(max_examples=100)
def test_p2_cors_origins_roundtrip(origins: list[str]):
    """
    Feature: diagno-pilot-improvements, Property 2:
    Pour toute liste non vide d'URLs d'origines valides, joindre par virgule
    puis parser via get_allowed_origins() doit reproduire exactement la liste
    d'origine (ordre préservé, espaces ignorés).
    """
    joined = ",".join(origins)
    s = Settings(ENV="development", ALLOWED_ORIGINS=joined)
    parsed = s.get_allowed_origins()
    assert parsed == origins, (
        f"Round-trip failed: input={origins!r}, joined={joined!r}, parsed={parsed!r}"
    )
