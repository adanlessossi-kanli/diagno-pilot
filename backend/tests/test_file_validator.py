# Feature: diagno-pilot-improvements, Property 4: FileValidator rejette tout fichier dépassant 20 Mo
# Feature: diagno-pilot-improvements, Property 5: FileValidator rejette les MIME types non autorisés
# Feature: diagno-pilot-improvements, Property 6: FileValidator rejette les noms de fichier avec traversée de répertoire
"""
Tests de propriété pour FileValidator — Diagno-Pilot

Property 4 : FileValidator rejette tout fichier dépassant 20 Mo
**Validates: Requirements 3.1**

Property 5 : FileValidator rejette les MIME types non autorisés
**Validates: Requirements 3.2, 3.3**

Property 6 : FileValidator rejette les noms de fichier avec traversée de répertoire
**Validates: Requirements 3.5**
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from hypothesis import HealthCheck, given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from backend.core.file_validator import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    FileValidator,
)

# ---------------------------------------------------------------------------
# Hypothesis profile
# ---------------------------------------------------------------------------

h_settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
h_settings.load_profile("ci")

validator = FileValidator()

# ---------------------------------------------------------------------------
# Property 4 — Taille > 20 Mo → HTTP 413
# ---------------------------------------------------------------------------

# Strategy: integers strictly greater than MAX_FILE_SIZE_BYTES
oversized_strategy = st.integers(min_value=MAX_FILE_SIZE_BYTES + 1, max_value=MAX_FILE_SIZE_BYTES + 10_000_000)


@given(size=oversized_strategy)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_p4_validate_size_rejects_oversized_files(size: int):
    """
    Feature: diagno-pilot-improvements, Property 4:
    Pour tout entier size > MAX_FILE_SIZE_BYTES, validate_size() doit lever
    une HTTPException avec status_code 413.

    **Validates: Requirements 3.1**
    """
    with pytest.raises(HTTPException) as exc_info:
        validator.validate_size(size)
    assert exc_info.value.status_code == 413, (
        f"Expected 413 for size={size}, got {exc_info.value.status_code}"
    )


def test_p4_validate_size_accepts_exact_limit():
    """Sanity check: a file exactly at the limit must not be rejected."""
    validator.validate_size(MAX_FILE_SIZE_BYTES)  # should not raise


def test_p4_validate_size_accepts_below_limit():
    """Sanity check: a file below the limit must not be rejected."""
    validator.validate_size(MAX_FILE_SIZE_BYTES - 1)  # should not raise


# ---------------------------------------------------------------------------
# Property 5 — MIME type non autorisé → HTTP 415
# ---------------------------------------------------------------------------

# MIME types that are NOT in the allowed set
DISALLOWED_MIME_TYPES = [
    "application/octet-stream",
    "text/html",
    "text/plain",
    "application/json",
    "application/xml",
    "video/mp4",
    "audio/mpeg",
    "application/zip",
    "image/gif",
    "image/webp",
]

disallowed_mime_strategy = st.sampled_from(DISALLOWED_MIME_TYPES)


@given(detected_mime=disallowed_mime_strategy)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_p5_validate_mime_rejects_disallowed_types(detected_mime: str):
    """
    Feature: diagno-pilot-improvements, Property 5:
    Pour tout MIME type détecté qui n'est pas dans ALLOWED_MIME_TYPES,
    validate_mime() doit lever une HTTPException avec status_code 415.

    **Validates: Requirements 3.2**
    """
    assert detected_mime not in ALLOWED_MIME_TYPES, (
        f"Test setup error: {detected_mime!r} is in ALLOWED_MIME_TYPES"
    )

    # Patch _detect_mime so the test works regardless of whether libmagic is installed
    with patch("backend.core.file_validator._detect_mime", return_value=detected_mime):
        with pytest.raises(HTTPException) as exc_info:
            validator.validate_mime(b"some content", declared_mime=None)
        assert exc_info.value.status_code == 415, (
            f"Expected 415 for MIME={detected_mime!r}, got {exc_info.value.status_code}"
        )


@given(
    allowed_mime=st.sampled_from(sorted(ALLOWED_MIME_TYPES)),
    declared_mime=disallowed_mime_strategy,
)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_p5_validate_mime_rejects_mismatch(allowed_mime: str, declared_mime: str):
    """
    Feature: diagno-pilot-improvements, Property 5:
    Lorsque le MIME type détecté est autorisé mais diffère du MIME type déclaré,
    validate_mime() doit lever une HTTPException avec status_code 415.

    **Validates: Requirements 3.3**
    """
    # Patch _detect_mime to return an allowed MIME type
    with patch("backend.core.file_validator._detect_mime", return_value=allowed_mime):
        with pytest.raises(HTTPException) as exc_info:
            validator.validate_mime(b"some content", declared_mime=declared_mime)
        assert exc_info.value.status_code == 415, (
            f"Expected 415 for detected={allowed_mime!r} vs declared={declared_mime!r}, "
            f"got {exc_info.value.status_code}"
        )


def test_p5_validate_mime_accepts_allowed_type_no_declared():
    """Sanity check: allowed MIME with no declared type must not raise."""
    with patch("backend.core.file_validator._detect_mime", return_value="application/pdf"):
        validator.validate_mime(b"%PDF-1.4 content", declared_mime=None)  # should not raise


def test_p5_validate_mime_accepts_matching_declared():
    """Sanity check: allowed MIME matching declared type must not raise."""
    with patch("backend.core.file_validator._detect_mime", return_value="image/jpeg"):
        validator.validate_mime(b"\xff\xd8\xff content", declared_mime="image/jpeg")  # should not raise


# ---------------------------------------------------------------------------
# Property 6 — Traversée de répertoire dans le nom de fichier → HTTP 400
# ---------------------------------------------------------------------------

# Strategy: filenames containing ../ or ..\ at arbitrary positions
_TRAVERSAL_SEQUENCES = ["../", "..\\"]

traversal_filename_strategy = st.one_of(
    # Sequence at the start
    st.builds(
        lambda seq, suffix: seq + suffix,
        seq=st.sampled_from(_TRAVERSAL_SEQUENCES),
        suffix=st.text(min_size=0, max_size=20),
    ),
    # Sequence in the middle
    st.builds(
        lambda prefix, seq, suffix: prefix + seq + suffix,
        prefix=st.text(min_size=1, max_size=10),
        seq=st.sampled_from(_TRAVERSAL_SEQUENCES),
        suffix=st.text(min_size=0, max_size=10),
    ),
    # Sequence at the end
    st.builds(
        lambda prefix, seq: prefix + seq,
        prefix=st.text(min_size=1, max_size=20),
        seq=st.sampled_from(_TRAVERSAL_SEQUENCES),
    ),
    # Multiple sequences
    st.builds(
        lambda a, seq1, b, seq2, c: a + seq1 + b + seq2 + c,
        a=st.text(min_size=0, max_size=5),
        seq1=st.sampled_from(_TRAVERSAL_SEQUENCES),
        b=st.text(min_size=0, max_size=5),
        seq2=st.sampled_from(_TRAVERSAL_SEQUENCES),
        c=st.text(min_size=0, max_size=5),
    ),
)


@given(filename=traversal_filename_strategy)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_p6_validate_filename_rejects_path_traversal(filename: str):
    """
    Feature: diagno-pilot-improvements, Property 6:
    Pour tout nom de fichier contenant ../ ou ..\\ (à n'importe quelle position),
    validate_filename() doit lever une HTTPException avec status_code 400.

    **Validates: Requirements 3.5**
    """
    with pytest.raises(HTTPException) as exc_info:
        validator.validate_filename(filename)
    assert exc_info.value.status_code == 400, (
        f"Expected 400 for filename={filename!r}, got {exc_info.value.status_code}"
    )


def test_p6_validate_filename_accepts_safe_names():
    """Sanity check: safe filenames must not be rejected."""
    safe_names = [
        "report.pdf",
        "image.jpg",
        "data.csv",
        "document.xlsx",
        "file_name-2024.png",
        "..hidden_file",   # starts with .. but no slash/backslash after
        "file..name.pdf",  # double dot in middle without slash
    ]
    for name in safe_names:
        validator.validate_filename(name)  # should not raise
