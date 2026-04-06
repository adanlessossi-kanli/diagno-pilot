"""
SourceLoaderService — per-format document loaders producing LlamaIndex Documents.

Dispatches to format-specific loaders (PDF, DOCX, CSV, TXT, HTML) and attaches
disease tags and document_type metadata.

Implements Requirements 3.1–3.8.
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Any

from llama_index.core.schema import Document

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (reused from document_service.py)
# ---------------------------------------------------------------------------

DISEASE_KEYWORDS: set[str] = {
    "malaria", "paludisme", "typhoid", "typhoïde", "dengue",
    "cholera", "choléra", "tuberculosis", "tuberculose", "hiv", "vih",
    "schistosomiasis", "bilharziose", "trypanosomiasis", "trypanosomiase",
    "yellow fever", "fièvre jaune", "meningitis", "méningite",
}


class SourceLoaderService:
    """Dispatches to format-specific loaders and returns LlamaIndex Documents."""

    SUPPORTED_FORMATS: set[str] = {"pdf", "docx", "csv", "txt", "html"}

    def load(
        self,
        content: bytes,
        filename: str,
        source: str,
        region: str = "ALL",
    ) -> list[Document]:
        """Load content and return LlamaIndex Documents with metadata.

        Raises ``ValueError`` for unsupported formats with a descriptive message.
        """
        ext = self._get_extension(filename)
        if ext not in self.SUPPORTED_FORMATS:
            supported = ", ".join(sorted(self.SUPPORTED_FORMATS))
            raise ValueError(
                f"Unsupported format: .{ext}. Supported formats: {supported}"
            )

        loader_map = {
            "pdf": self._load_pdf,
            "docx": self._load_docx,
            "csv": self._load_csv,
            "txt": self._load_txt,
            "html": self._load_html,
        }
        docs = loader_map[ext](content)

        # Attach common metadata
        doc_type = self._infer_document_type(source)
        for doc in docs:
            doc.metadata["source"] = source
            doc.metadata["region"] = region
            doc.metadata["document_type"] = doc_type

        # Attach disease tags based on full text
        full_text = " ".join(d.text for d in docs)
        self._attach_disease_tags(docs, full_text)

        return docs

    # ------------------------------------------------------------------
    # Format-specific loaders
    # ------------------------------------------------------------------

    def _load_pdf(self, content: bytes) -> list[Document]:
        """Load PDF using pypdf, one Document per page."""
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        docs: list[Document] = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                docs.append(Document(text=text, metadata={"page": i}))
        return docs if docs else [Document(text="", metadata={"page": 0})]

    def _load_docx(self, content: bytes) -> list[Document]:
        """Load DOCX using python-docx, preserving heading hierarchy."""
        from docx import Document as DocxDocument

        doc = DocxDocument(io.BytesIO(content))
        parts: list[str] = []
        current_section: str | None = None
        metadata: dict[str, Any] = {}

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            if para.style and para.style.name and para.style.name.startswith("Heading"):
                current_section = text
            parts.append(text)

        full_text = "\n".join(parts)
        if current_section:
            metadata["section"] = current_section
        return [Document(text=full_text, metadata=metadata)] if full_text.strip() else [Document(text="", metadata={})]

    def _load_csv(self, content: bytes) -> list[Document]:
        """Load CSV preserving column headers and row structure."""
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = [", ".join(row) for row in reader if any(cell.strip() for cell in row)]
        full_text = "\n".join(rows)
        return [Document(text=full_text, metadata={})]

    def _load_txt(self, content: bytes) -> list[Document]:
        """Load plain text file."""
        text = content.decode("utf-8", errors="replace")
        return [Document(text=text, metadata={})]

    def _load_html(self, content: bytes) -> list[Document]:
        """Load HTML content using BeautifulSoup, extracting main text."""
        from bs4 import BeautifulSoup

        text_str = content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(text_str, "html.parser")

        # Remove script and style elements
        for tag in soup(["script", "style"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        return [Document(text=text, metadata={})]

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    def _attach_disease_tags(self, docs: list[Document], text: str) -> None:
        """Tag documents with matching DISEASE_KEYWORDS found in text."""
        text_lower = text.lower()
        tags = sorted(kw for kw in DISEASE_KEYWORDS if kw in text_lower)
        for doc in docs:
            doc.metadata["disease_tags"] = tags

    @staticmethod
    def _infer_document_type(source: str) -> str:
        """Infer document type from the source organisation name.

        Reuses the exact logic from document_service.infer_document_type.
        """
        s = source.upper()
        if "PNLP" in s or "MSF" in s:
            return "protocol"
        if "CHU" in s or "OMS" in s or "WHO" in s:
            return "guideline"
        return "other"

    @staticmethod
    def _get_extension(filename: str) -> str:
        """Extract lowercase extension from filename."""
        if "." in filename:
            return filename.rsplit(".", 1)[-1].lower()
        return ""
