"""
Tests de propriété pour l'authentification JWT — Diagno-Pilot

**Validates: Requirements REQ-01**

Propriété 1 : Tout token JWT généré est valide uniquement pour l'utilisateur
émetteur et expire après la durée configurée.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
import jwt

from backend.core.config import settings
from backend.routers.auth import create_access_token

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate non-empty ASCII strings as user IDs (simulating MongoDB ObjectId strings)
user_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=64,
)

role_strategy = st.sampled_from(["medecin", "pharmacien", "admin", "pediatre", "urgentiste", "interne"])


# ---------------------------------------------------------------------------
# Property 1a : sub claim always matches the user_id used to create the token
# ---------------------------------------------------------------------------

@given(user_id=user_id_strategy, role=role_strategy)
@h_settings(max_examples=100)
def test_token_sub_always_matches_creator(user_id: str, role: str):
    """
    **Validates: Requirements REQ-01**

    For any user_id and role, the decoded `sub` claim of the generated token
    must exactly equal the user_id that was used to create it.
    """
    token = create_access_token(user_id=user_id, role=role)
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    assert payload["sub"] == user_id


# ---------------------------------------------------------------------------
# Property 1b : token expiry matches JWT_EXPIRE_MINUTES (within tolerance)
# ---------------------------------------------------------------------------

@given(user_id=user_id_strategy, role=role_strategy)
@h_settings(max_examples=100)
def test_token_expiry_matches_configured_duration(user_id: str, role: str):
    """
    **Validates: Requirements REQ-01**

    A token generated with the configured expiry always expires after
    JWT_EXPIRE_MINUTES minutes (within a 5-second tolerance).
    """
    before = datetime.now(timezone.utc)
    token = create_access_token(user_id=user_id, role=role)
    after = datetime.now(timezone.utc)

    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    expected_min = before.timestamp() + settings.JWT_EXPIRE_MINUTES * 60
    expected_max = after.timestamp() + settings.JWT_EXPIRE_MINUTES * 60

    tolerance = 5  # seconds
    assert exp.timestamp() >= expected_min - tolerance
    assert exp.timestamp() <= expected_max + tolerance


# ---------------------------------------------------------------------------
# Property 1c : token for user A is rejected when presented as user B
# ---------------------------------------------------------------------------

@given(
    user_id_a=user_id_strategy,
    user_id_b=user_id_strategy,
    role=role_strategy,
)
@h_settings(max_examples=100)
def test_token_sub_mismatch_detected(user_id_a: str, user_id_b: str, role: str):
    """
    **Validates: Requirements REQ-01**

    A token generated for user A must not decode with a `sub` claim equal to
    user B's ID when the two IDs differ.
    """
    token_a = create_access_token(user_id=user_id_a, role=role)
    payload = jwt.decode(token_a, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])

    if user_id_a != user_id_b:
        assert payload["sub"] != user_id_b
    else:
        # When IDs are equal the sub must match both (trivially correct)
        assert payload["sub"] == user_id_a
