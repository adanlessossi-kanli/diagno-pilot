"""
DocumentService — ingestion, chunking, embedding and indexing of medical documents.
Supports PDF, DOCX, TXT, CSV formats.
Implements REQ-05 (medical knowledge base).
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from typing import Optional

from bson import ObjectId
from fastapi import UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.models.document import MedicalDocument
from backend.services.embedding_model import EmbeddingModel
from backend.services.encryption_service import EncryptionService
from backend.services.index_manager import IndexManager
from backend.services.phi_classifier import PHIClassifier
from backend.services.s3_service import S3Service
from backend.services.semantic_chunker import SemanticChunkerService
from backend.services.source_loaders import SourceLoaderService
from backend.core.db_metrics import timed_db_op

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_SIZE = 500        # characters per chunk
CHUNK_OVERLAP = 50      # overlap between consecutive chunks
SUPPORTED_FORMATS = {"pdf", "docx", "txt", "csv"}

DISEASE_KEYWORDS = {
    "malaria", "paludisme", "typhoid", "typhoïde", "dengue",
    "cholera", "choléra", "tuberculosis", "tuberculose", "hiv", "vih",
    "schistosomiasis", "bilharziose", "trypanosomiasis", "trypanosomiase",
    "yellow fever", "fièvre jaune", "meningitis", "méningite",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def infer_document_type(source: str) -> str:
    """Infer document type from the source organisation name."""
    s = source.upper()
    if "PNLP" in s or "MSF" in s:
        return "protocol"
    if "CHU" in s or "OMS" in s or "WHO" in s:
        return "guideline"
    return "other"


# ---------------------------------------------------------------------------
# CrossEncoder singleton
# ---------------------------------------------------------------------------

_cross_encoder = None


def get_cross_encoder():
    """Lazily load and cache the CrossEncoder model."""
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _cross_encoder


# ---------------------------------------------------------------------------
# PDF BBox extraction data structures
# ---------------------------------------------------------------------------

@dataclass
class PdfPageData:
    """Text and character-level bbox data for a single PDF page."""
    page_number: int          # 0-based page index
    text: str                 # full extracted text for this page
    char_bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    # char_bboxes[i] = (x0, y0, x1, y1) for character at position i in text


@dataclass
class PdfChunkBBox:
    """BBox and offset metadata for a single chunk extracted from a PDF."""
    bbox: list[float]          # [x0, y0, x1, y1] bounding box of the chunk text
    page: int                  # 0-based page number
    page_char_start: int       # character offset within the page text
    page_char_end: int         # character offset within the page text (exclusive)


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_pdf(content: bytes) -> str:
    """Extract plain text from a PDF file (no bbox)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for PDF extraction. Run: pip install pypdf") from exc

    reader = PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text)
    return "\n".join(parts)


def _extract_pdf_pages_with_bbox(content: bytes) -> list[PdfPageData]:
    """Extract text and per-character bounding boxes from a PDF using pypdf.

    Returns a list of PdfPageData (one per page) with:
    - text: the full extracted text for the page
    - char_bboxes: list of (x0, y0, x1, y1) tuples, one per character in text

    Falls back to text-only (empty char_bboxes) if bbox extraction fails for a page.
    Requirements: 5.1
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for PDF extraction. Run: pip install pypdf") from exc

    reader = PdfReader(io.BytesIO(content))
    pages: list[PdfPageData] = []

    for page_idx, page in enumerate(reader.pages):
        page_data = PdfPageData(page_number=page_idx, text="")
        try:
            # Use pypdf's visitor-based extraction to get character positions
            char_texts: list[str] = []
            char_bboxes: list[tuple[float, float, float, float]] = []

            def _visitor(text: str, cm: object, tm: object, font_dict: object, font_size: float) -> None:  # noqa: ANN001
                """Visitor callback called by pypdf for each text chunk."""
                if not text:
                    return
                # tm is the text matrix [a, b, c, d, e, f] where (e, f) is position
                tm_seq: list[float] | tuple[float, ...] | None = tm if isinstance(tm, (list, tuple)) else None  # type: ignore[assignment]
                if tm_seq is not None and len(tm_seq) >= 6:
                    x0 = float(tm_seq[4])
                    y0 = float(tm_seq[5])
                    # Approximate width per character using font_size
                    char_width = float(font_size) * 0.5 if font_size else 6.0
                    char_height = float(font_size) if font_size else 12.0
                    for ch in text:
                        char_texts.append(ch)
                        char_bboxes.append((x0, y0, x0 + char_width, y0 + char_height))
                        x0 += char_width
                else:
                    for ch in text:
                        char_texts.append(ch)
                        char_bboxes.append((0.0, 0.0, 0.0, 0.0))

            page.extract_text(visitor_text=_visitor)
            page_data.text = "".join(char_texts)
            page_data.char_bboxes = char_bboxes
        except Exception:
            # Fallback: plain text extraction without bbox
            page_data.text = page.extract_text() or ""
            page_data.char_bboxes = []

        pages.append(page_data)

    return pages


def _compute_chunk_bbox(
    page_data: PdfPageData,
    char_start: int,
    char_end: int,
) -> Optional[list[float]]:
    """Compute the bounding box for a text span [char_start, char_end) on a page.

    Returns [x0, y0, x1, y1] as the union of all character bboxes in the span,
    or None if bbox data is unavailable.
    """
    if not page_data.char_bboxes or char_start >= char_end:
        return None
    end = min(char_end, len(page_data.char_bboxes))
    start = min(char_start, end)
    if start >= end:
        return None
    span_bboxes = page_data.char_bboxes[start:end]
    # Filter out zero-bboxes (fallback entries)
    valid = [(x0, y0, x1, y1) for (x0, y0, x1, y1) in span_bboxes if x1 > x0 or y1 > y0]
    if not valid:
        # Return a minimal bbox from the first entry
        x0, y0, x1, y1 = span_bboxes[0]
        return [x0, y0, x1, y1]
    x0 = min(b[0] for b in valid)
    y0 = min(b[1] for b in valid)
    x1 = max(b[2] for b in valid)
    y1 = max(b[3] for b in valid)
    return [x0, y0, x1, y1]


def _extract_text_docx(content: bytes) -> str:
    """Extract plain text from a DOCX file."""
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("python-docx is required for DOCX extraction. Run: pip install python-docx") from exc

    doc = Document(io.BytesIO(content))
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def _extract_text_txt(content: bytes) -> str:
    """Decode a plain-text file."""
    return content.decode("utf-8", errors="replace")


def _extract_text_csv(content: bytes) -> str:
    """Convert CSV rows to a readable text block."""
    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = [", ".join(row) for row in reader if any(cell.strip() for cell in row)]
    return "\n".join(rows)


def extract_text(content: bytes, extension: str) -> str:
    """Dispatch text extraction based on file extension."""
    ext = extension.lower().lstrip(".")
    if ext == "pdf":
        return _extract_text_pdf(content)
    if ext == "docx":
        return _extract_text_docx(content)
    if ext in ("txt", "text"):
        return _extract_text_txt(content)
    if ext == "csv":
        return _extract_text_csv(content)
    raise ValueError(f"Unsupported file format: {ext}. Supported: {SUPPORTED_FORMATS}")

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split *text* into overlapping chunks of *chunk_size* characters."""
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


# ---------------------------------------------------------------------------
# DocumentService
# ---------------------------------------------------------------------------

class DocumentService:
    """Handles ingestion, indexing, listing and deletion of medical documents."""

    def __init__(
        self,
        database: AsyncIOMotorDatabase,
        embedder: EmbeddingModel,
        s3: S3Service,
        source_loader: SourceLoaderService | None = None,
        semantic_chunker: SemanticChunkerService | None = None,
        index_manager: IndexManager | None = None,
        encryption_service: EncryptionService | None = None,
        phi_classifier: PHIClassifier | None = None,
    ) -> None:
        self._db = database
        self._docs = database["medical_documents"]
        self._chunks = database["document_chunks"]
        self._embedder = embedder
        self._s3 = s3
        self._source_loader = source_loader or SourceLoaderService()
        self._semantic_chunker = semantic_chunker or SemanticChunkerService(embed_model=embedder)
        self._index_manager = index_manager or IndexManager(db=database)
        self._encryption_service = encryption_service
        self._phi_classifier = phi_classifier or PHIClassifier()
        # Load CrossEncoder singleton at startup (best-effort)
        try:
            get_cross_encoder()
        except ImportError:
            logger.warning("sentence_transformers not available; CrossEncoder will not be loaded.")

    # ------------------------------------------------------------------
    # Startup checks
    # ------------------------------------------------------------------

    async def check_unmigrated_chunks(self) -> None:
        """Detect chunks missing enriched metadata and log a warning.

        Counts document_chunks where any of metadata.disease_tags,
        metadata.document_type, or metadata.evidence_level is absent or null.
        Logs a WARNING with the count — does NOT trigger automatic migration.
        Implements REQ 6.1.
        """
        query = {
            "$or": [
                {"metadata.disease_tags": {"$exists": False}},
                {"metadata.disease_tags": None},
                {"metadata.document_type": {"$exists": False}},
                {"metadata.document_type": None},
                {"metadata.evidence_level": {"$exists": False}},
                {"metadata.evidence_level": None},
            ]
        }
        count = await self._chunks.count_documents(query)
        if count > 0:
            logger.warning(
                "[Migration] %d chunk(s) sans métadonnées enrichies "
                "(disease_tags, document_type, evidence_level). "
                "Exécutez POST /api/v1/admin/migrate-chunks pour migrer.",
                count,
            )

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    async def ingest(
        self,
        file: UploadFile,
        title: str,
        source: str,
        region: str = "ALL",
    ) -> MedicalDocument:
        """Ingest a document: load → chunk → embed → store in MongoDB + S3.

        Uses the new LlamaIndex pipeline:
        1. SourceLoaderService — format-specific loading with metadata extraction
        2. SemanticChunkerService — semantic splitting into TextNodes
        3. IndexManager.insert_nodes() — incremental index update
        4. EncryptionService — encrypt PHI fields on patient-annotated chunks

        Returns the persisted MedicalDocument.
        """
        content = await file.read()
        filename = file.filename or "unknown"
        extension = filename.rsplit(".", 1)[-1] if "." in filename else "txt"

        # Use filename (without extension) as title if none provided
        if not title:
            title = filename.rsplit(".", 1)[0] if "." in filename else filename

        ext = extension.lower().lstrip(".")

        # 1. Load via SourceLoaderService (format-specific, with metadata)
        documents = self._source_loader.load(content, filename, source, region)

        # Also extract text for legacy compatibility (PDF bbox path)
        pdf_pages: list[PdfPageData] | None = None
        if ext == "pdf":
            pdf_pages = _extract_pdf_pages_with_bbox(content)

        # 2. Upload source file to S3 under documents/ prefix
        s3_key = await self._upload_to_s3(content, filename, file.content_type or "application/octet-stream")

        # 3. Persist document metadata (without chunk_count yet)
        doc_id = ObjectId()
        now = datetime.now(timezone.utc)
        doc_record = {
            "_id": doc_id,
            "title": title,
            "source": source,
            "s3_key": s3_key,
            "indexed_at": now,
            "chunk_count": 0,
            "created_at": now,
        }
        async with timed_db_op("medical_documents", "insert_one"):
            await self._docs.insert_one(doc_record)

        # 4. Chunk via SemanticChunkerService
        nodes = self._semantic_chunker.chunk(documents)

        # 5. Build chunk records and embed
        chunk_count = await self._index_chunks_llamaindex(
            nodes, doc_id, source, region=region, pdf_pages=pdf_pages,
        )

        # 6. Update chunk_count
        async with timed_db_op("medical_documents", "update_one"):
            await self._docs.update_one({"_id": doc_id}, {"$set": {"chunk_count": chunk_count}})

        return MedicalDocument(
            id=str(doc_id),
            title=title,
            source=source,
            s3_key=s3_key,
            indexed_at=now,
            chunk_count=chunk_count,
            created_at=now,
        )

    async def _upload_to_s3(self, content: bytes, filename: str, content_type: str) -> str:
        """Upload raw bytes to S3 under the documents/ prefix and return the key."""
        file_id = uuid.uuid4().hex
        key = f"documents/{file_id}_{filename}"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            partial(
                self._s3._client.put_object,
                Bucket=self._s3._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            ),
        )
        return key

    async def _index_chunks_llamaindex(
        self,
        nodes: list,
        doc_id: ObjectId,
        source: str,
        region: str = "ALL",
        pdf_pages: list[PdfPageData] | None = None,
    ) -> int:
        """Embed each TextNode and insert via IndexManager. Returns count inserted.

        Applies EncryptionService.encrypt_phi_fields() on patient-annotated
        chunk metadata before storage (Requirement 7.1).
        """
        if not nodes:
            return 0

        document_type = infer_document_type(source)
        evidence_level = document_type

        # Build cumulative page offsets for PDF bbox mapping
        page_cumulative_lengths: list[int] | None = None
        if pdf_pages is not None:
            page_cumulative_lengths = []
            cumulative = 0
            for p in pdf_pages:
                page_cumulative_lengths.append(cumulative)
                cumulative += len(p.text) + 1  # +1 for "\n" separator

        records: list[dict] = []
        global_char_offset = 0

        for node in nodes:
            embedding = await self._embedder.encode(node.text)
            content_lower = node.text.lower()
            disease_tags = [kw for kw in DISEASE_KEYWORDS if kw in content_lower]

            # Merge metadata from the TextNode with enriched fields
            node_meta = dict(node.metadata) if node.metadata else {}
            metadata: dict = {
                "source": node_meta.get("source", source),
                "page": node_meta.get("page"),
                "section": node_meta.get("section"),
                "region": node_meta.get("region", region),
                "disease_tags": node_meta.get("disease_tags", disease_tags),
                "document_type": node_meta.get("document_type", document_type),
                "evidence_level": evidence_level,
                "bbox": None,
                "page_char_start": None,
                "page_char_end": None,
            }

            # PDF-specific: extract bbox and character offsets
            if pdf_pages is not None and page_cumulative_lengths is not None:
                chunk_len = len(node.text)
                chunk_global_start = global_char_offset
                chunk_global_end = global_char_offset + chunk_len

                page_idx = 0
                for i, cum in enumerate(page_cumulative_lengths):
                    if cum <= chunk_global_start:
                        page_idx = i
                    else:
                        break

                if page_idx < len(pdf_pages):
                    page = pdf_pages[page_idx]
                    page_start_global = page_cumulative_lengths[page_idx]
                    page_char_start = chunk_global_start - page_start_global
                    page_char_end = min(
                        chunk_global_end - page_start_global,
                        len(page.text),
                    )
                    bbox = _compute_chunk_bbox(page, page_char_start, page_char_end)

                    metadata["page"] = page_idx
                    metadata["page_char_start"] = page_char_start
                    metadata["page_char_end"] = page_char_end
                    metadata["bbox"] = bbox if bbox is not None else [0.0, 0.0, 0.0, 0.0]

                global_char_offset += chunk_len + 1
            else:
                global_char_offset += len(node.text) + 1

            # Encrypt PHI fields on patient-annotated chunks (Req 7.1)
            if self._encryption_service is not None:
                try:
                    metadata = self._encryption_service.encrypt_phi_fields(
                        metadata, self._phi_classifier
                    )
                except Exception:
                    logger.warning("PHI encryption failed for chunk; storing unencrypted metadata")

            records.append({
                "_id": ObjectId(),
                "document_id": doc_id,
                "content": node.text,
                "embedding": embedding,
                "metadata": metadata,
            })

        if records:
            count = await self._index_manager.insert_nodes(records)
            return count

        return 0

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_documents(self) -> list[MedicalDocument]:
        """Return all indexed medical documents."""
        async with timed_db_op("medical_documents", "find"):
            cursor = self._docs.find({}).sort("created_at", -1)
            docs = await cursor.to_list(length=None)
        return [
            MedicalDocument(
                id=str(d["_id"]),
                title=d["title"],
                source=d["source"],
                s3_key=d.get("s3_key"),
                indexed_at=d.get("indexed_at"),
                chunk_count=d.get("chunk_count", 0),
                created_at=d.get("created_at"),
            )
            for d in docs
        ]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and all its chunks. Also removes the S3 file.

        Returns True if the document was found and deleted, False otherwise.
        """
        try:
            oid = ObjectId(document_id)
        except Exception:
            return False

        async with timed_db_op("medical_documents", "find_one"):
            doc = await self._docs.find_one({"_id": oid})
        if doc is None:
            return False

        # Remove S3 file
        s3_key = doc.get("s3_key")
        if s3_key:
            await self._delete_from_s3(s3_key)

        # Remove chunks
        async with timed_db_op("document_chunks", "delete_one"):
            await self._chunks.delete_many({"document_id": oid})

        # Remove document record
        async with timed_db_op("medical_documents", "delete_one"):
            await self._docs.delete_one({"_id": oid})

        return True

    async def _delete_from_s3(self, key: str) -> None:
        """Delete an object from S3, ignoring errors."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                partial(
                    self._s3._client.delete_object,
                    Bucket=self._s3._bucket,
                    Key=key,
                ),
            )
        except Exception:
            pass  # best-effort deletion
