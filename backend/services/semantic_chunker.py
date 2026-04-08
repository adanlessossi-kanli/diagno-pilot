"""
SemanticChunkerService — LlamaIndex-based semantic chunker.

Replaces ``backend/services/chunker.py`` with token-aware, semantically coherent
splitting that preserves table boundaries, numbered step grouping, and section
metadata.

Implements Requirements 2.1–2.7.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import tiktoken
from llama_index.core.schema import Document, TextNode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_SECTION_HEADER_RE = re.compile(r"^(\#{1,3}\s+.+|[A-Z][A-Za-zÀ-ÿ ]{2,}:)\s*$", re.MULTILINE)
_NUMBERED_STEP_RE = re.compile(r"^(\d+[\.\)])\s", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|.*\|", re.MULTILINE)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")

# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

_ENCODER: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def _count_tokens(text: str) -> int:
    return len(_get_encoder().encode(text))


# ---------------------------------------------------------------------------
# SemanticChunkerService
# ---------------------------------------------------------------------------

class SemanticChunkerService:
    """Token-aware semantic chunker producing LlamaIndex TextNodes."""

    def __init__(
        self,
        embed_model: Any = None,
        max_tokens: int = 512,
    ) -> None:
        self._embed_model = embed_model
        self._max_tokens = max_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk(self, documents: list[Document]) -> list[TextNode]:
        """Split documents into semantically coherent TextNodes with metadata."""
        all_nodes: list[TextNode] = []
        for doc in documents:
            nodes = self._split_document(doc)
            all_nodes.extend(nodes)

        all_nodes = self._preserve_table_boundaries(all_nodes)
        all_nodes = self._preserve_step_numbering(all_nodes)
        return all_nodes

    # ------------------------------------------------------------------
    # Core splitting
    # ------------------------------------------------------------------

    def _split_document(self, doc: Document) -> list[TextNode]:
        """Split a single Document into TextNodes respecting token limits."""
        text = doc.text
        if not text or not text.strip():
            return []

        base_meta = dict(doc.metadata) if doc.metadata else {}

        # Split into logical segments (sections, paragraphs)
        segments = self._segment_text(text)

        nodes: list[TextNode] = []
        for segment_text, section_header in segments:
            if not segment_text.strip():
                continue
            meta = dict(base_meta)
            if section_header:
                meta["section"] = section_header

            # If segment fits within token limit, emit as single node
            if _count_tokens(segment_text) <= self._max_tokens:
                nodes.append(TextNode(text=segment_text, metadata=meta))
            else:
                # Split further at sentence boundaries
                sub_chunks = self._split_by_sentences(segment_text)
                for chunk_text in sub_chunks:
                    if chunk_text.strip():
                        nodes.append(TextNode(text=chunk_text, metadata=dict(meta)))

        return nodes

    def _segment_text(self, text: str) -> list[tuple[str, str | None]]:
        """Split text into (segment_text, section_header) tuples.

        Segments are delimited by section headers. The header line is included
        in the segment text so round-trip concatenation preserves all content.
        """
        lines = text.split("\n")
        segments: list[tuple[str, str | None]] = []
        current_lines: list[str] = []
        current_header: str | None = None

        for line in lines:
            stripped = line.strip()
            if _SECTION_HEADER_RE.match(stripped + "\n") or (
                stripped and _SECTION_HEADER_RE.match(stripped + " \n")
            ):
                # Check if this looks like a real header
                is_header = bool(re.match(r"^#{1,3}\s+", stripped))
                if not is_header and stripped.endswith(":") and stripped[0].isupper():
                    is_header = True

                if is_header:
                    # Flush current segment
                    if current_lines:
                        seg_text = "\n".join(current_lines)
                        segments.append((seg_text, current_header))
                    current_lines = [line]
                    current_header = stripped.rstrip(":")
                    continue

            current_lines.append(line)

        # Flush remaining
        if current_lines:
            seg_text = "\n".join(current_lines)
            segments.append((seg_text, current_header))

        return segments if segments else [(text, None)]

    def _split_by_sentences(self, text: str) -> list[str]:
        """Split text into chunks at sentence boundaries within token limit."""
        sentences = _SENTENCE_END_RE.split(text)
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            sent_tokens = _count_tokens(sentence)

            if sent_tokens > self._max_tokens:
                # Flush current buffer
                if current:
                    chunks.append(" ".join(current))
                    current = []
                    current_tokens = 0
                # Hard-split oversized sentence by tokens
                chunks.extend(self._hard_split(sentence))
                continue

            if current_tokens + sent_tokens > self._max_tokens and current:
                chunks.append(" ".join(current))
                current = []
                current_tokens = 0

            current.append(sentence)
            current_tokens += sent_tokens

        if current:
            chunks.append(" ".join(current))

        return chunks

    def _hard_split(self, text: str) -> list[str]:
        """Split text that exceeds max_tokens by encoding and decoding token windows."""
        encoder = _get_encoder()
        tokens = encoder.encode(text)
        chunks: list[str] = []
        for i in range(0, len(tokens), self._max_tokens):
            window = tokens[i : i + self._max_tokens]
            chunks.append(encoder.decode(window))
        return chunks

    # ------------------------------------------------------------------
    # Post-processors
    # ------------------------------------------------------------------

    def _preserve_table_boundaries(self, nodes: list[TextNode]) -> list[TextNode]:
        """Merge adjacent table-row nodes and re-split if they exceed token limit."""
        if not nodes:
            return nodes

        result: list[TextNode] = []
        i = 0
        while i < len(nodes):
            node = nodes[i]
            if not _TABLE_ROW_RE.search(node.text):
                result.append(node)
                i += 1
                continue

            # Collect consecutive table nodes
            table_lines: list[str] = [node.text]
            meta = dict(node.metadata)
            j = i + 1
            while j < len(nodes) and _TABLE_ROW_RE.search(nodes[j].text):
                table_lines.append(nodes[j].text)
                j += 1

            merged = "\n".join(table_lines)
            if _count_tokens(merged) <= self._max_tokens:
                result.append(TextNode(text=merged, metadata=meta))
            else:
                # Split at row boundaries within token limit
                current_rows: list[str] = []
                current_tok = 0
                for row_text in table_lines:
                    row_tok = _count_tokens(row_text)
                    if current_tok + row_tok > self._max_tokens and current_rows:
                        result.append(TextNode(text="\n".join(current_rows), metadata=dict(meta)))
                        current_rows = []
                        current_tok = 0
                    current_rows.append(row_text)
                    current_tok += row_tok
                if current_rows:
                    result.append(TextNode(text="\n".join(current_rows), metadata=dict(meta)))

            i = j

        return result

    def _preserve_step_numbering(self, nodes: list[TextNode]) -> list[TextNode]:
        """Ensure numbered steps that were split across nodes are re-grouped."""
        if not nodes:
            return nodes

        result: list[TextNode] = []
        i = 0
        while i < len(nodes):
            node = nodes[i]
            # Check if this node starts with a numbered step
            if not _NUMBERED_STEP_RE.match(node.text.strip()):
                result.append(node)
                i += 1
                continue

            # Collect consecutive step nodes that fit within token limit
            step_parts: list[str] = [node.text]
            meta = dict(node.metadata)
            total_tokens = _count_tokens(node.text)
            j = i + 1

            while j < len(nodes):
                next_text = nodes[j].text.strip()
                next_tokens = _count_tokens(next_text)
                # If next node is a numbered step or continuation, try to merge
                if _NUMBERED_STEP_RE.match(next_text):
                    if total_tokens + next_tokens <= self._max_tokens:
                        step_parts.append(nodes[j].text)
                        total_tokens += next_tokens
                        j += 1
                    else:
                        break
                else:
                    break

            merged = "\n".join(step_parts)
            result.append(TextNode(text=merged, metadata=meta))
            i = j

        return result
