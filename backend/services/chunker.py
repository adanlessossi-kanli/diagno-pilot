"""
Semantic chunker for the RAG pipeline.
Splits document text into semantically coherent passages aligned to section headers,
numbered steps, and table boundaries.
Implements Requirements 3.1, 3.2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SECTION_HEADER_RE = re.compile(r'^(\d+\.|\#{1,3}|\*{1,2})[^\n]+', re.MULTILINE)
NUMBERED_STEP_RE = re.compile(r'^(\d+[\.\)])\s', re.MULTILINE)
MAX_CHUNK_CHARS = 800

# Sentence boundary: period, exclamation, or question mark followed by space or end of string
_SENTENCE_END_RE = re.compile(r'[.!?](?:\s|$)')


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ChunkResult:
    content: str
    section: str | None  # section header or table caption


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

class Chunker:
    """Splits text into semantically coherent chunks of at most MAX_CHUNK_CHARS characters."""

    def chunk(self, text: str) -> list[ChunkResult]:
        """Return a list of ChunkResult with content and section fields."""
        if not text or not text.strip():
            return []

        lines = text.splitlines(keepends=True)
        results: list[ChunkResult] = []
        current_section: str | None = None
        buffer: str = ""
        table_buffer: str = ""
        in_table: bool = False

        def _flush_buffer(buf: str, section: str | None) -> None:
            """Split buf at sentence boundaries up to MAX_CHUNK_CHARS and append to results."""
            buf = buf.strip()
            if not buf:
                return
            while len(buf) > MAX_CHUNK_CHARS:
                # Find the last sentence boundary within MAX_CHUNK_CHARS
                window = buf[:MAX_CHUNK_CHARS]
                match = None
                for m in _SENTENCE_END_RE.finditer(window):
                    match = m
                if match:
                    split_pos = match.end()
                    chunk_content = buf[:split_pos].strip()
                    if chunk_content:
                        results.append(ChunkResult(content=chunk_content, section=section))
                    buf = buf[split_pos:].strip()
                else:
                    # No sentence boundary found — hard split at MAX_CHUNK_CHARS
                    results.append(ChunkResult(content=window.strip(), section=section))
                    buf = buf[MAX_CHUNK_CHARS:].strip()
            if buf:
                results.append(ChunkResult(content=buf, section=section))

        def _flush_table(tbl: str, section: str | None) -> None:
            tbl = tbl.strip()
            if not tbl:
                return
            # Table chunks may exceed MAX_CHUNK_CHARS; split at row boundaries if needed
            rows = tbl.splitlines(keepends=True)
            chunk_rows: list[str] = []
            chunk_len = 0
            for row in rows:
                if chunk_len + len(row) > MAX_CHUNK_CHARS and chunk_rows:
                    results.append(ChunkResult(content="".join(chunk_rows).strip(), section=section))
                    chunk_rows = []
                    chunk_len = 0
                chunk_rows.append(row)
                chunk_len += len(row)
            if chunk_rows:
                results.append(ChunkResult(content="".join(chunk_rows).strip(), section=section))

        for line in lines:
            stripped = line.rstrip('\n').rstrip('\r')

            # --- Table row detection ---
            if '|' in stripped:
                if not in_table:
                    # Flush any pending non-table buffer first
                    _flush_buffer(buffer, current_section)
                    buffer = ""
                    in_table = True
                table_buffer += line
                continue
            else:
                if in_table:
                    # End of table block — flush table buffer
                    _flush_table(table_buffer, current_section)
                    table_buffer = ""
                    in_table = False

            # --- Section header detection ---
            if SECTION_HEADER_RE.match(stripped):
                # Flush current buffer before starting new section
                _flush_buffer(buffer, current_section)
                buffer = ""
                current_section = stripped.strip()
                # The header itself starts the new buffer
                buffer = line
                continue

            # --- Numbered step detection ---
            if NUMBERED_STEP_RE.match(stripped):
                # Flush current buffer, then start new chunk with this step
                _flush_buffer(buffer, current_section)
                buffer = line
                continue

            # --- Accumulate into buffer ---
            if len(buffer) + len(line) > MAX_CHUNK_CHARS:
                _flush_buffer(buffer, current_section)
                buffer = line
            else:
                buffer += line

        # Flush any remaining content
        if in_table:
            _flush_table(table_buffer, current_section)
        _flush_buffer(buffer, current_section)

        return results
