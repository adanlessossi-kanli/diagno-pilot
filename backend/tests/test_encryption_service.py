"""
Tests de propriété pour le service de chiffrement — Diagno-Pilot

# Feature: llm-llamaindex-hipaa-refactor, Property 9: Encryption round-trip
# Feature: llm-llamaindex-hipaa-refactor, Property 10: Encryption failure safety

**Validates: Requirements 7.1, 7.5, 7.6**
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.encryption_service import EncryptionError, EncryptionService
from backend.services.phi_classifier import PHIClassifier

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

classifier = PHIClassifier()


def _make_service() -> EncryptionService:
    """Create an EncryptionService with a fresh random key."""
    return EncryptionService()


# Strategies — valid UTF-8 strings (Fernet operates on bytes)
plaintext_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
    ),
    min_size=0,
    max_size=500,
)

# Strategy for PHI field names
phi_field_strategy = st.sampled_from(sorted(PHIClassifier.PHI_FIELDS))

# Strategy for non-PHI field names
non_phi_field_strategy = st.sampled_from(sorted(PHIClassifier.NON_PHI_FIELDS))


# ---------------------------------------------------------------------------
# Property 9a: Single-field encrypt → decrypt round-trip
# ---------------------------------------------------------------------------

@given(plaintext=plaintext_strategy)
@h_settings(max_examples=100)
def test_encrypt_decrypt_roundtrip(plaintext: str):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 9: Encryption round-trip
    **Validates: Requirements 7.1, 7.5**

    For any valid string, encrypt_field then decrypt_field must return
    the original string.
    """
    svc = _make_service()
    ciphertext = svc.encrypt_field(plaintext)
    assert svc.decrypt_field(ciphertext) == plaintext


# ---------------------------------------------------------------------------
# Property 9b: Ciphertext differs from plaintext (non-trivial encryption)
# ---------------------------------------------------------------------------

@given(plaintext=plaintext_strategy.filter(lambda s: len(s) > 0))
@h_settings(max_examples=100)
def test_ciphertext_differs_from_plaintext(plaintext: str):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 9: Encryption round-trip
    **Validates: Requirements 7.1**

    For any non-empty string, the ciphertext must differ from the plaintext.
    """
    svc = _make_service()
    ciphertext = svc.encrypt_field(plaintext)
    assert ciphertext != plaintext


# ---------------------------------------------------------------------------
# Property 9c: Bulk encrypt_phi_fields → decrypt_phi_fields round-trip
# ---------------------------------------------------------------------------

@given(
    data=st.dictionaries(
        keys=st.one_of(phi_field_strategy, non_phi_field_strategy),
        values=st.text(min_size=0, max_size=50),
        min_size=1,
        max_size=8,
    )
)
@h_settings(max_examples=100)
def test_bulk_phi_encrypt_decrypt_roundtrip(data: dict):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 9: Encryption round-trip
    **Validates: Requirements 7.1, 7.5**

    For any dict with PHI and non-PHI fields, encrypting then decrypting
    PHI fields must return the original data.
    """
    svc = _make_service()
    encrypted = svc.encrypt_phi_fields(data, classifier)
    decrypted = svc.decrypt_phi_fields(encrypted, classifier)
    assert decrypted == data


# ---------------------------------------------------------------------------
# Property 9d: Non-PHI fields are not modified by encrypt_phi_fields
# ---------------------------------------------------------------------------

@given(
    data=st.dictionaries(
        keys=non_phi_field_strategy,
        values=st.text(min_size=0, max_size=50),
        min_size=1,
        max_size=5,
    )
)
@h_settings(max_examples=100)
def test_non_phi_fields_unchanged(data: dict):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 9: Encryption round-trip
    **Validates: Requirements 7.1**

    Non-PHI fields must pass through encrypt_phi_fields unchanged.
    """
    svc = _make_service()
    encrypted = svc.encrypt_phi_fields(data, classifier)
    assert encrypted == data


# ---------------------------------------------------------------------------
# Property 9e: Key rotation — old ciphertext still decryptable
# ---------------------------------------------------------------------------

@given(plaintext=plaintext_strategy)
@h_settings(max_examples=100)
def test_key_rotation_decrypts_old_ciphertext(plaintext: str):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 9: Encryption round-trip
    **Validates: Requirements 7.4**

    After key rotation, ciphertext encrypted with the old key must still
    be decryptable.
    """
    svc = _make_service()
    ciphertext = svc.encrypt_field(plaintext)

    new_key = Fernet.generate_key().decode()
    svc.rotate_key(new_key)

    # Old ciphertext still decryptable via fallback
    assert svc.decrypt_field(ciphertext) == plaintext

    # New encryption uses new key
    new_ciphertext = svc.encrypt_field(plaintext)
    assert svc.decrypt_field(new_ciphertext) == plaintext


# ---------------------------------------------------------------------------
# Property 10a: Invalid ciphertext raises EncryptionError
# ---------------------------------------------------------------------------

@given(garbage=st.text(min_size=1, max_size=200))
@h_settings(max_examples=100)
def test_invalid_ciphertext_raises_error(garbage: str):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 10: Encryption failure safety
    **Validates: Requirements 7.6**

    For any invalid ciphertext, decrypt_field must raise EncryptionError
    without exposing plaintext.
    """
    svc = _make_service()
    with pytest.raises(EncryptionError):
        svc.decrypt_field(garbage)


# ---------------------------------------------------------------------------
# Property 10b: Error message does not contain original plaintext
# ---------------------------------------------------------------------------

@given(plaintext=plaintext_strategy.filter(lambda s: len(s) > 3))
@h_settings(max_examples=100)
def test_error_does_not_expose_plaintext(plaintext: str):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 10: Encryption failure safety
    **Validates: Requirements 7.6**

    When decryption fails, the error message must not contain the original
    plaintext that was encrypted.
    """
    svc = _make_service()
    ciphertext = svc.encrypt_field(plaintext)

    # Create a different service with a different key — decryption will fail
    svc2 = _make_service()
    try:
        svc2.decrypt_field(ciphertext)
        # If it somehow decrypts (astronomically unlikely with different keys),
        # that's fine — the property is about error messages.
    except EncryptionError as exc:
        assert plaintext not in str(exc)
