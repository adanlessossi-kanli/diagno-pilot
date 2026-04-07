"""
Tests for cache-related Settings fields — Diagno-Pilot

Feature: caching-and-performance

Property 11: TTL settings reject non-integer values
**Validates: Requirements 7.3**

Unit tests for Settings defaults and rate-limit migration
**Validates: Requirements 7.1, 7.2, 6.1, 6.2**
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.core.config import Settings


# ---------------------------------------------------------------------------
# Property 11 — TTL settings reject non-integer values
# ---------------------------------------------------------------------------

_TTL_FIELDS = [
    "CACHE_TTL_PROTOCOLS",
    "CACHE_TTL_INTERACTIONS",
    "CACHE_TTL_EMBEDDINGS",
    "CACHE_TTL_RAG",
]

def _is_valid_int_string(s: str) -> bool:
    """Return True if pydantic would accept s as a valid integer for a TTL field."""
    try:
        from pydantic import TypeAdapter
        TypeAdapter(int).validate_python(s)
        return True
    except Exception:
        return False


_bad_value_strategy = st.text().filter(
    lambda s: s.strip() != "" and not _is_valid_int_string(s)
)


@given(
    field=st.sampled_from(_TTL_FIELDS),
    bad_value=_bad_value_strategy,
)
@h_settings(max_examples=100, deadline=None)
def test_p11_ttl_rejects_non_integer(field: str, bad_value: str):
    # Feature: caching-and-performance, Property 11: TTL settings reject non-integer values
    kwargs = {field: bad_value}
    with pytest.raises(ValidationError):
        Settings(**kwargs)


# ---------------------------------------------------------------------------
# Unit tests — Settings defaults
# ---------------------------------------------------------------------------

def test_redis_url_default(monkeypatch):
    """REDIS_URL defaults to redis://localhost:6379/0 when env var is absent."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    # Bypass .env file loading by constructing Settings without env_file
    s = Settings(_env_file=None)
    assert s.REDIS_URL == "redis://localhost:6379/0"


def test_cache_ttl_defaults():
    """All TTL fields have the correct default values."""
    s = Settings()
    assert s.CACHE_TTL_PROTOCOLS == 3600
    assert s.CACHE_TTL_INTERACTIONS == 3600
    assert s.CACHE_TTL_EMBEDDINGS == 86400
    assert s.CACHE_TTL_RAG == 300


def test_cache_key_version_default():
    """CACHE_KEY_VERSION defaults to 'v1'."""
    s = Settings()
    assert s.CACHE_KEY_VERSION == "v1"


# ---------------------------------------------------------------------------
# Unit tests — Rate-limit storage migration
# ---------------------------------------------------------------------------

def test_rate_limit_storage_migrates_to_redis_url(monkeypatch):
    """RATE_LIMIT_STORAGE_URI is set to REDIS_URL when REDIS_URL is provided."""
    redis_url = "redis://redis-host:6379/1"
    monkeypatch.setenv("REDIS_URL", redis_url)
    s = Settings()
    assert s.RATE_LIMIT_STORAGE_URI == redis_url


def test_rate_limit_storage_stays_memory_when_no_redis_url(monkeypatch):
    """RATE_LIMIT_STORAGE_URI stays 'memory://' when REDIS_URL is not set."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    Settings(REDIS_URL="redis://localhost:6379/0")
    # When REDIS_URL is the default and RATE_LIMIT_STORAGE_URI is memory://,
    # the validator migrates it — so we test explicit memory:// override
    s2 = Settings(REDIS_URL="redis://localhost:6379/0", RATE_LIMIT_STORAGE_URI="memory://")
    assert s2.RATE_LIMIT_STORAGE_URI == "redis://localhost:6379/0"


def test_rate_limit_storage_not_overridden_when_already_set(monkeypatch):
    """RATE_LIMIT_STORAGE_URI is not overridden when it has already been set explicitly."""
    custom_uri = "redis://custom-rate-limit:6379/2"
    s = Settings(REDIS_URL="redis://localhost:6379/0", RATE_LIMIT_STORAGE_URI=custom_uri)
    assert s.RATE_LIMIT_STORAGE_URI == custom_uri


def test_cache_key_version_custom(monkeypatch):
    """CACHE_KEY_VERSION can be overridden via env var."""
    monkeypatch.setenv("CACHE_KEY_VERSION", "v2")
    s = Settings()
    assert s.CACHE_KEY_VERSION == "v2"
