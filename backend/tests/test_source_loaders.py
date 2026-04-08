"""
Tests de propriété pour les Source Loaders — Diagno-Pilot

# Feature: llm-llamaindex-hipaa-refactor, Properties 4 & 5

**Validates: Requirements 3.6, 3.7, 3.8**
"""
from __future__ import annotations

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.source_loaders import (
    DISEASE_KEYWORDS,
    SourceLoaderService,
)

loader = SourceLoaderService()

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Organisation names that map to known document types
protocol_orgs = st.sampled_from(["PNLP", "MSF", "pnlp-togo", "msf-france"])
guideline_orgs = st.sampled_from(["CHU", "OMS", "WHO", "chu-lome", "oms-afro"])
other_orgs = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),
    min_size=1,
    max_size=20,
).filter(
    lambda s: not any(
        kw in s.upper() for kw in ("PNLP", "MSF", "CHU", "OMS", "WHO")
    )
)

# Disease keywords strategy — pick a subset to embed in text
disease_subset = st.frozensets(st.sampled_from(sorted(DISEASE_KEYWORDS)), min_size=0, max_size=5)

# Base text that does NOT contain any disease keywords
safe_alphabet = st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"), blacklist_characters="")
base_text = st.text(alphabet=safe_alphabet, min_size=1, max_size=200).filter(
    lambda t: not any(kw in t.lower() for kw in DISEASE_KEYWORDS)
)

# Unsupported extensions — not in {pdf, docx, csv, txt, html}
unsupported_ext = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),
    min_size=1,
    max_size=10,
).filter(lambda e: e not in SourceLoaderService.SUPPORTED_FORMATS)


# ---------------------------------------------------------------------------
# Property 4: Source loader metadata extraction
# ---------------------------------------------------------------------------

@given(
    text=base_text,
    keywords=disease_subset,
    source=st.one_of(protocol_orgs, guideline_orgs, other_orgs),
)
@h_settings(max_examples=100)
def test_property_4_disease_tags_and_document_type(
    text: str, keywords: frozenset[str], source: str
):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 4: Source loader metadata extraction
    **Validates: Requirements 3.7, 3.8**

    For any document text and source organisation name, disease tags matching
    DISEASE_KEYWORDS are correctly extracted, and document_type is inferred
    correctly (PNLP/MSF → "protocol", CHU/OMS/WHO → "guideline", otherwise → "other").
    """
    # Build text with embedded keywords
    parts = [text] + list(keywords)
    full_text = " ".join(parts)
    content = full_text.encode("utf-8")

    docs = loader.load(content, "test.txt", source=source, region="ALL")

    # Check document_type inference
    s_upper = source.upper()
    if "PNLP" in s_upper or "MSF" in s_upper:
        expected_type = "protocol"
    elif "CHU" in s_upper or "OMS" in s_upper or "WHO" in s_upper:
        expected_type = "guideline"
    else:
        expected_type = "other"

    for doc in docs:
        assert doc.metadata["document_type"] == expected_type, (
            f"Expected document_type={expected_type!r} for source={source!r}, "
            f"got {doc.metadata['document_type']!r}"
        )

    # Check disease tags — every keyword we embedded should be detected
    combined_text_lower = " ".join(d.text for d in docs).lower()
    for kw in keywords:
        if kw in combined_text_lower:
            for doc in docs:
                assert kw in doc.metadata["disease_tags"], (
                    f"Keyword {kw!r} present in text but missing from disease_tags"
                )

    # No spurious tags — every tag must actually appear in the text
    for doc in docs:
        for tag in doc.metadata["disease_tags"]:
            assert tag in combined_text_lower, (
                f"Tag {tag!r} in disease_tags but not found in text"
            )


# ---------------------------------------------------------------------------
# Property 5: Unsupported format error message
# ---------------------------------------------------------------------------

@given(ext=unsupported_ext)
@h_settings(max_examples=100)
def test_property_5_unsupported_format_error(ext: str):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 5: Unsupported format error message
    **Validates: Requirements 3.6**

    For any file with an extension not in {pdf, docx, csv, txt, html}, the
    error message contains the unsupported extension and lists all supported formats.
    """
    filename = f"document.{ext}"
    content = b"some content"

    try:
        loader.load(content, filename, source="TestOrg")
        assert False, f"Expected ValueError for extension .{ext}"
    except ValueError as exc:
        msg = str(exc)
        # Error must mention the unsupported extension
        assert ext in msg, (
            f"Error message should contain the extension {ext!r}: {msg}"
        )
        # Error must list all supported formats
        for fmt in SourceLoaderService.SUPPORTED_FORMATS:
            assert fmt in msg, (
                f"Error message should list supported format {fmt!r}: {msg}"
            )
