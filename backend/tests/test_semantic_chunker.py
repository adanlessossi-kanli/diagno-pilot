"""
Tests de propriété pour le Semantic Chunker — Diagno-Pilot

# Feature: llm-llamaindex-hipaa-refactor, Properties 1, 2 & 3

**Validates: Requirements 2.2, 2.3, 2.6, 2.7**
"""
from __future__ import annotations


from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st
from llama_index.core.schema import Document

from backend.services.semantic_chunker import SemanticChunkerService, _count_tokens

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Printable text without surrogates, min 1 char
printable_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_categories=("Cs",),
    ),
    min_size=1,
    max_size=2000,
).filter(lambda t: t.strip())

# Max token counts — reasonable range
max_token_strategy = st.integers(min_value=50, max_value=1024)

# Source metadata for Property 3
source_strategy = st.sampled_from(["PNLP", "MSF", "CHU", "OMS", "WHO", "HospitalX"])
region_strategy = st.sampled_from(["TG", "BJ", "ALL"])
section_header_strategy = st.from_regex(r"^#{1,3} [A-Za-z][A-Za-z0-9 ]{0,30}", fullmatch=True)


# ---------------------------------------------------------------------------
# Property 1: Chunking round-trip preserves text content
# ---------------------------------------------------------------------------

@given(text=printable_text)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_1_chunking_round_trip(text: str):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 1: Chunking round-trip preserves text content
    **Validates: Requirements 2.7**

    For any valid document text, chunking then concatenating all chunk contents
    preserves all original text content without loss.
    """
    chunker = SemanticChunkerService(max_tokens=512)
    docs = [Document(text=text, metadata={})]
    nodes = chunker.chunk(docs)

    # Concatenate all node texts
    reconstructed = " ".join(n.text for n in nodes)

    # Normalize whitespace for comparison — chunking may reformat whitespace
    # but must preserve all non-whitespace content
    original_words = set(text.split())
    reconstructed_words = set(reconstructed.split())

    # Every word from the original must appear in the reconstruction
    missing = original_words - reconstructed_words
    assert not missing, (
        f"Words lost during chunking: {missing!r}"
    )


# ---------------------------------------------------------------------------
# Property 2: Chunk token limit invariant
# ---------------------------------------------------------------------------

@given(text=printable_text, max_tokens=max_token_strategy)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_2_chunk_token_limit(text: str, max_tokens: int):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 2: Chunk token limit invariant
    **Validates: Requirements 2.3**

    For any valid document text and configured max token count, all chunks
    have token count <= max.
    """
    chunker = SemanticChunkerService(max_tokens=max_tokens)
    docs = [Document(text=text, metadata={})]
    nodes = chunker.chunk(docs)

    for node in nodes:
        token_count = _count_tokens(node.text)
        assert token_count <= max_tokens, (
            f"Chunk has {token_count} tokens, exceeds max_tokens={max_tokens}. "
            f"Chunk text (first 100 chars): {node.text[:100]!r}"
        )


# ---------------------------------------------------------------------------
# Property 3: Chunk metadata preservation
# ---------------------------------------------------------------------------

@given(
    body=printable_text,
    header=section_header_strategy,
    source=source_strategy,
    region=region_strategy,
)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_3_chunk_metadata_preservation(
    body: str, header: str, source: str, region: str
):
    """
    # Feature: llm-llamaindex-hipaa-refactor, Property 3: Chunk metadata preservation
    **Validates: Requirements 2.2, 2.6**

    For any document with source metadata, all chunk nodes carry the source
    metadata, and nodes with section headers have section field populated.
    """
    # Build document with a section header
    text = f"{header}\n{body}"
    doc = Document(
        text=text,
        metadata={
            "document_id": "doc123",
            "source": source,
            "region": region,
            "page": 0,
        },
    )

    chunker = SemanticChunkerService(max_tokens=512)
    nodes = chunker.chunk([doc])

    assert len(nodes) > 0, "Chunker must produce at least one node"

    for node in nodes:
        # Source metadata must be preserved on every node
        assert node.metadata.get("source") == source, (
            f"Expected source={source!r}, got {node.metadata.get('source')!r}"
        )
        assert node.metadata.get("region") == region, (
            f"Expected region={region!r}, got {node.metadata.get('region')!r}"
        )
        assert node.metadata.get("document_id") == "doc123"

    # At least one node containing the header text should have section populated
    header_nodes = [n for n in nodes if header.lstrip("#").strip() in n.text]
    if header_nodes:
        sections = [n.metadata.get("section") for n in header_nodes]
        assert any(s is not None for s in sections), (
            f"No node with header text has section metadata set. "
            f"Header: {header!r}, sections: {sections}"
        )
