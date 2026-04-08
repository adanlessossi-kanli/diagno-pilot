"""
Tests pour le service de chiffrement AES-256-GCM — Diagno-Pilot

Couvre les propriétés de correction (Hypothesis) et les tests unitaires
pour la migration Fernet → AES-256-GCM.

# Feature: best-practices-hardening, Property 2: AES-256-GCM round-trip
# Feature: best-practices-hardening, Property 3: AES-256-GCM nonce uniqueness
# Feature: best-practices-hardening, Property 4: Key rotation preserves decryption

Validates: Requirements 10.1–10.7
"""
from __future__ import annotations

import base64
import os

import pytest
from cryptography.fernet import Fernet
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.encryption_service import EncryptionError, EncryptionService
from backend.services.phi_classifier import PHIClassifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

classifier = PHIClassifier()


def _make_key() -> str:
    """Generate a random AES-256-GCM key (32 bytes, base64url)."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def _make_service() -> EncryptionService:
    """Create an EncryptionService with a fresh random AES-256-GCM key."""
    return EncryptionService()


# Strategies
plaintext_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=0,
    max_size=500,
)

phi_field_strategy = st.sampled_from(sorted(PHIClassifier.PHI_FIELDS))
non_phi_field_strategy = st.sampled_from(sorted(PHIClassifier.NON_PHI_FIELDS))


# ===========================================================================
# Property 2: AES-256-GCM round-trip (Requirement 10.6)
# ===========================================================================


@given(plaintext=plaintext_strategy)
@h_settings(max_examples=100)
def test_aesgcm_encrypt_decrypt_roundtrip(plaintext: str):
    """
    # Feature: best-practices-hardening, Property 2: AES-256-GCM round-trip
    **Validates: Requirement 10.6**

    For any valid UTF-8 string, encrypt_field then decrypt_field must
    return the original string.
    """
    svc = _make_service()
    ciphertext = svc.encrypt_field(plaintext)
    assert svc.decrypt_field(ciphertext) == plaintext


@given(plaintext=plaintext_strategy.filter(lambda s: len(s) > 0))
@h_settings(max_examples=100)
def test_ciphertext_differs_from_plaintext(plaintext: str):
    """
    # Feature: best-practices-hardening, Property 2: AES-256-GCM round-trip
    **Validates: Requirement 10.1**

    For any non-empty string, the ciphertext must differ from the plaintext.
    """
    svc = _make_service()
    ciphertext = svc.encrypt_field(plaintext)
    assert ciphertext != plaintext


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
    # Feature: best-practices-hardening, Property 2: AES-256-GCM round-trip
    **Validates: Requirement 10.6**

    For any dict with PHI and non-PHI fields, encrypting then decrypting
    PHI fields must return the original data.
    """
    svc = _make_service()
    encrypted = svc.encrypt_phi_fields(data, classifier)
    decrypted = svc.decrypt_phi_fields(encrypted, classifier)
    assert decrypted == data


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
    """Non-PHI fields must pass through encrypt_phi_fields unchanged."""
    svc = _make_service()
    encrypted = svc.encrypt_phi_fields(data, classifier)
    assert encrypted == data


# ===========================================================================
# Property 3: AES-256-GCM nonce uniqueness (Requirement 10.2)
# ===========================================================================


@given(plaintext=plaintext_strategy)
@h_settings(max_examples=100)
def test_aesgcm_nonce_uniqueness(plaintext: str):
    """
    # Feature: best-practices-hardening, Property 3: AES-256-GCM nonce uniqueness
    **Validates: Requirement 10.2**

    Two successive encryptions of the same string must produce different
    ciphertexts (because nonces are randomly generated).
    """
    svc = _make_service()
    ct1 = svc.encrypt_field(plaintext)
    ct2 = svc.encrypt_field(plaintext)
    assert ct1 != ct2


# ===========================================================================
# Property 4: Key rotation preserves decryption (Requirement 10.5)
# ===========================================================================


@given(plaintext=plaintext_strategy)
@h_settings(max_examples=100)
def test_key_rotation_preserves_decryption(plaintext: str):
    """
    # Feature: best-practices-hardening, Property 4: Key rotation preserves decryption
    **Validates: Requirement 10.5**

    After rotating to a new key, ciphertext encrypted with the old key
    must still be decryptable.
    """
    svc = _make_service()
    ciphertext = svc.encrypt_field(plaintext)

    new_key = _make_key()
    svc.rotate_key(new_key)

    # Old ciphertext still decryptable via fallback
    assert svc.decrypt_field(ciphertext) == plaintext

    # New encryption uses new key and also round-trips
    new_ct = svc.encrypt_field(plaintext)
    assert svc.decrypt_field(new_ct) == plaintext


# ===========================================================================
# Unit tests: Fernet fallback compatibility (Requirements 10.3, 10.4)
# ===========================================================================


class TestFernetFallback:
    """Verify that data encrypted with the old Fernet scheme can still be
    decrypted after migration to AES-256-GCM."""

    def test_decrypt_legacy_fernet_token(self):
        """Ciphertext produced by Fernet must be decryptable via fallback.

        Validates: Requirement 10.3
        """
        fernet_key = Fernet.generate_key()
        fernet = Fernet(fernet_key)
        plaintext = "patient-name-legacy"
        fernet_token = fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

        # Fernet tokens start with gAAAAA
        assert fernet_token.startswith("gAAAAA")

        # Create AES-GCM service, then simulate migration: old Fernet key
        # becomes the _previous_fernet fallback.
        svc = _make_service()
        svc._previous_fernet = fernet

        assert svc.decrypt_field(fernet_token) == plaintext

    def test_fernet_fallback_after_rotation(self):
        """After rotation from Fernet-era, legacy tokens remain decryptable.

        Validates: Requirement 10.4
        """
        fernet_key = Fernet.generate_key()
        fernet = Fernet(fernet_key)
        plaintext = "legacy-phi-data"
        fernet_token = fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

        svc = _make_service()
        svc._previous_fernet = fernet

        # Rotate to yet another AES-GCM key — Fernet fallback should persist
        new_key = _make_key()
        svc.rotate_key(new_key)

        assert svc.decrypt_field(fernet_token) == plaintext


# ===========================================================================
# Unit tests: Ciphertext format (Requirement 10.2)
# ===========================================================================


class TestCiphertextFormat:
    """Verify the AES-256-GCM ciphertext format: base64url(nonce[12] || ct+tag)."""

    def test_ciphertext_is_base64url(self):
        svc = _make_service()
        ct = svc.encrypt_field("hello")
        # Should decode without error
        raw = base64.urlsafe_b64decode(ct)
        assert len(raw) > 12  # at least nonce + some ciphertext

    def test_nonce_is_12_bytes(self):
        svc = _make_service()
        ct = svc.encrypt_field("test-data")
        raw = base64.urlsafe_b64decode(ct)
        nonce = raw[:12]
        assert len(nonce) == 12

    def test_different_encryptions_have_different_nonces(self):
        svc = _make_service()
        ct1 = svc.encrypt_field("same")
        ct2 = svc.encrypt_field("same")
        raw1 = base64.urlsafe_b64decode(ct1)
        raw2 = base64.urlsafe_b64decode(ct2)
        assert raw1[:12] != raw2[:12]


# ===========================================================================
# Unit tests: Invalid key (Requirement 10.3)
# ===========================================================================


class TestInvalidKey:
    """Verify that invalid keys are rejected."""

    def test_key_too_short_raises_valueerror(self):
        short_key = base64.urlsafe_b64encode(os.urandom(16)).decode()
        with pytest.raises(ValueError, match="32 bytes"):
            EncryptionService(key=short_key)

    def test_key_too_long_raises_valueerror(self):
        long_key = base64.urlsafe_b64encode(os.urandom(64)).decode()
        with pytest.raises(ValueError, match="32 bytes"):
            EncryptionService(key=long_key)

    def test_none_key_generates_valid_service(self):
        svc = EncryptionService(key=None)
        ct = svc.encrypt_field("works")
        assert svc.decrypt_field(ct) == "works"


# ===========================================================================
# Error handling
# ===========================================================================


@given(garbage=st.text(min_size=1, max_size=200))
@h_settings(max_examples=100)
def test_invalid_ciphertext_raises_error(garbage: str):
    """Invalid ciphertext must raise EncryptionError."""
    svc = _make_service()
    with pytest.raises(EncryptionError):
        svc.decrypt_field(garbage)


@given(plaintext=plaintext_strategy.filter(lambda s: len(s) > 3))
@h_settings(max_examples=100)
def test_error_does_not_expose_plaintext(plaintext: str):
    """Error message must not contain the original plaintext."""
    svc = _make_service()
    ciphertext = svc.encrypt_field(plaintext)

    svc2 = _make_service()
    try:
        svc2.decrypt_field(ciphertext)
    except EncryptionError as exc:
        assert plaintext not in str(exc)
