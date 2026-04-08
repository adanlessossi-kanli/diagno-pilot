"""
Tests for HIPAA-related Settings validation — LLM LlamaIndex HIPAA Refactor

Validates: Requirements 11.4, 11.5
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.core.config import Settings

# Common kwargs that satisfy all existing production validators (JWT, CORS)
_PROD_BASE = dict(
    ENV="production",
    JWT_SECRET="a]secure_production_secret_key_that_is_long_enough",
    ALLOWED_ORIGINS="https://app.example.com",
)


# ---------------------------------------------------------------------------
# Requirement 11.4 — Production rejects missing HIPAA_ENCRYPTION_KEY_ID
# ---------------------------------------------------------------------------

def test_production_rejects_missing_hipaa_encryption_key_id():
    """HIPAA_ENCRYPTION_KEY_ID must be set when ENV=production."""
    with pytest.raises((ValidationError, ValueError), match="HIPAA_ENCRYPTION_KEY_ID"):
        Settings(
            **_PROD_BASE,
            HIPAA_ENCRYPTION_KEY_ID="",
            HIPAA_PHI_STRIP_ON_FALLBACK=True,
        )


def test_production_accepts_valid_hipaa_encryption_key_id():
    """A non-empty HIPAA_ENCRYPTION_KEY_ID passes production validation."""
    s = Settings(
        **_PROD_BASE,
        HIPAA_ENCRYPTION_KEY_ID="my-kms-key-id-123",
        HIPAA_PHI_STRIP_ON_FALLBACK=True,
    )
    assert s.HIPAA_ENCRYPTION_KEY_ID == "my-kms-key-id-123"


# ---------------------------------------------------------------------------
# Requirement 11.4 — Production rejects HIPAA_PHI_STRIP_ON_FALLBACK=False
# ---------------------------------------------------------------------------

def test_production_rejects_phi_strip_disabled():
    """HIPAA_PHI_STRIP_ON_FALLBACK must be True when ENV=production."""
    with pytest.raises((ValidationError, ValueError), match="HIPAA_PHI_STRIP_ON_FALLBACK"):
        Settings(
            **_PROD_BASE,
            HIPAA_ENCRYPTION_KEY_ID="my-key",
            HIPAA_PHI_STRIP_ON_FALLBACK=False,
        )


# ---------------------------------------------------------------------------
# Requirement 11.5 — Backward compatibility with existing env vars
# ---------------------------------------------------------------------------

def test_backward_compatibility_existing_llm_vars():
    """Existing LLM_PRIMARY_URL, LLM_PRIMARY_API_KEY etc. still work."""
    s = Settings(
        ENV="development",
        LLM_PRIMARY_URL="http://localhost:11434/v1",
        LLM_PRIMARY_API_KEY="old-key",
        LLM_FALLBACK_URL="https://api.openai.com/v1",
        LLM_FALLBACK_API_KEY="sk-old",
        EMBED_MODEL="text-embedding-3-small",
    )
    assert s.LLM_PRIMARY_URL == "http://localhost:11434/v1"
    assert s.LLM_PRIMARY_API_KEY == "old-key"
    assert s.LLM_FALLBACK_URL == "https://api.openai.com/v1"
    assert s.LLM_FALLBACK_API_KEY == "sk-old"
    assert s.EMBED_MODEL == "text-embedding-3-small"


def test_new_fields_have_sensible_defaults():
    """New Model_Container, LlamaIndex, and HIPAA fields have defaults."""
    s = Settings(ENV="development")
    assert s.MODEL_CONTAINER_URL == "http://model:8080/v1"
    assert s.MODEL_CONTAINER_API_KEY == ""
    assert s.MODEL_GPU_LAYERS == 99
    assert s.MODEL_CONTEXT_SIZE == 4096
    assert s.MODEL_THREADS == 4
    assert s.LLAMAINDEX_CHUNK_SIZE == 512
    assert s.LLAMAINDEX_CHUNK_OVERLAP_TOKENS == 50
    assert s.LLAMAINDEX_SIMILARITY_THRESHOLD == 0.75
    assert s.HIPAA_ENCRYPTION_KEY_ID == ""
    assert s.HIPAA_AUDIT_HASH_CHAIN_ENABLED is True
    assert s.HIPAA_PHI_STRIP_ON_FALLBACK is True


def test_hipaa_validation_skipped_in_development():
    """HIPAA validators do not fire outside production."""
    s = Settings(
        ENV="development",
        HIPAA_ENCRYPTION_KEY_ID="",
        HIPAA_PHI_STRIP_ON_FALLBACK=False,
    )
    assert s.HIPAA_ENCRYPTION_KEY_ID == ""
    assert s.HIPAA_PHI_STRIP_ON_FALLBACK is False
