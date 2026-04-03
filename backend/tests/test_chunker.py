"""
Unit and property-based tests for Chunker — Diagno-Pilot
Validates: Requirements 3.1, 3.2
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from backend.services.chunker import (
    Chunker,
    ChunkResult,
    MAX_CHUNK_CHARS,
    SECTION_HEADER_RE,
    NUMBERED_STEP_RE,
)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestChunkerUnit:
    def test_empty_text_returns_empty_list(self):
        chunker = Chunker()
        assert chunker.chunk("") == []

    def test_whitespace_only_returns_empty_list(self):
        chunker = Chunker()
        assert chunker.chunk("   \n\t  ") == []

    def test_short_text_returns_single_chunk(self):
        chunker = Chunker()
        text = "Short medical text under 800 chars."
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].content == text.strip()

    def test_section_header_detected_and_sets_section_field(self):
        chunker = Chunker()
        text = "## Traitement du paludisme\nAdministrer de l'artémisinine."
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        # At least one chunk should have the section set
        assert any(c.section == "## Traitement du paludisme" for c in chunks)

    def test_numbered_step_starts_new_chunk(self):
        chunker = Chunker()
        text = "Introduction.\n1. Première étape du traitement.\n2. Deuxième étape du traitement."
        chunks = chunker.chunk(text)
        # Numbered steps should trigger new chunks
        assert len(chunks) >= 2

    def test_table_rows_grouped_together(self):
        chunker = Chunker()
        text = "| Drug | Dose |\n| Amoxicillin | 500mg |\n| Ciprofloxacin | 250mg |"
        chunks = chunker.chunk(text)
        # All table rows should be in a single chunk (they fit within 800 chars)
        assert len(chunks) == 1
        assert "|" in chunks[0].content

    def test_long_text_split_into_multiple_chunks_all_within_limit(self):
        chunker = Chunker()
        # Generate text longer than MAX_CHUNK_CHARS
        text = "Medical content sentence. " * 100  # ~2600 chars
        chunks = chunker.chunk(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.content) <= MAX_CHUNK_CHARS

    def test_chunk_result_has_content_and_section_fields(self):
        chunker = Chunker()
        text = "# Section\nSome content here."
        chunks = chunker.chunk(text)
        assert all(isinstance(c, ChunkResult) for c in chunks)
        assert all(hasattr(c, "content") for c in chunks)
        assert all(hasattr(c, "section") for c in chunks)

    def test_hash_header_sets_section(self):
        chunker = Chunker()
        text = "# Introduction\nThis is the introduction."
        chunks = chunker.chunk(text)
        assert any(c.section == "# Introduction" for c in chunks)

    def test_numbered_section_header_sets_section(self):
        chunker = Chunker()
        text = "1. Diagnostic\nVoici les critères diagnostiques."
        chunks = chunker.chunk(text)
        assert any(c.section is not None for c in chunks)


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

# Feature: diagno-pilot-improvements, Property 8: Chunker respecte la taille maximale et les frontières sémantiques
# Validates: Requirements 3.1
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(text=st.text(min_size=1, max_size=5000))
def test_property_8_chunker_respects_max_size(text: str):
    chunker = Chunker()
    chunks = chunker.chunk(text)
    for chunk in chunks:
        assert len(chunk.content) <= MAX_CHUNK_CHARS


# Feature: diagno-pilot-improvements, Property 9: Préservation de l'en-tête de section dans metadata.section
# Validates: Requirements 3.2
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    header=st.from_regex(r'^#{1,3} [A-Za-z][A-Za-z0-9 ]{0,50}', fullmatch=True),
    body=st.text(min_size=1, max_size=400, alphabet=st.characters(blacklist_categories=('Cs',), blacklist_characters='|#*\n')),
)
def test_property_9_section_header_preserved_in_metadata(header: str, body: str):
    text = header + "\n" + body
    chunker = Chunker()
    chunks = chunker.chunk(text)
    # At least one chunk must have section == header (stripped)
    assert any(chunk.section == header.strip() for chunk in chunks)
