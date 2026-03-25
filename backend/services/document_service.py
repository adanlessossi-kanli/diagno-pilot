"""
DocumentService — ingestion, chunking, embedding and indexing of medical documents.
Supports PDF, DOCX, TXT, CSV formats.
Implements REQ-05 (medical knowledge base).
"""
from __future__ import annotations

import asyncio
import csv
import io
import uuid
from datetime import datetime, timezone
from functools import partial
from typing import AsyncIterator

import boto3
from bson import ObjectId
from fastapi import UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.core.config import settings
from backend.models.document import MedicalDocument
from backend.services.embedding_service import EmbeddingModel
from backend.services.s3_service import S3Service

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_SIZE = 500        # characters per chunk
CHUNK_OVERLAP = 50      # overlap between consecutive chunks
SUPPORTED_FORMATS = {"pdf", "docx", "txt", "csv"}


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_pdf(content: bytes) -> str:
    """Extract plain text from a PDF file."""
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
    ) -> None:
        self._db = database
        self._docs = database["medical_documents"]
        self._chunks = database["document_chunks"]
        self._embedder = embedder
        self._s3 = s3

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    async def ingest(
        self,
        file: UploadFile,
        title: str,
        source: str,
    ) -> MedicalDocument:
        """Ingest a document: extract text → chunk → embed → store in MongoDB + S3.

        Returns the persisted MedicalDocument.
        """
        content = await file.read()
        filename = file.filename or "unknown"
        extension = filename.rsplit(".", 1)[-1] if "." in filename else "txt"

        # Use filename (without extension) as title if none provided
        if not title:
            title = filename.rsplit(".", 1)[0] if "." in filename else filename

        # 1. Extract text
        text = extract_text(content, extension)

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
        await self._docs.insert_one(doc_record)

        # 4. Chunk, embed and insert into document_chunks
        chunks = chunk_text(text)
        chunk_count = await self._index_chunks(chunks, doc_id, source)

        # 5. Update chunk_count
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

    async def _index_chunks(
        self, chunks: list[str], doc_id: ObjectId, source: str
    ) -> int:
        """Embed each chunk and insert into document_chunks. Returns count inserted."""
        if not chunks:
            return 0

        records = []
        for i, chunk in enumerate(chunks):
            embedding = await self._embedder.encode(chunk)
            records.append({
                "_id": ObjectId(),
                "document_id": doc_id,
                "content": chunk,
                "embedding": embedding,
                "metadata": {
                    "source": source,
                    "page": None,
                    "section": f"chunk_{i}",
                },
            })

        if records:
            await self._chunks.insert_many(records)

        return len(records)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_documents(self) -> list[MedicalDocument]:
        """Return all indexed medical documents."""
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

        doc = await self._docs.find_one({"_id": oid})
        if doc is None:
            return False

        # Remove S3 file
        s3_key = doc.get("s3_key")
        if s3_key:
            await self._delete_from_s3(s3_key)

        # Remove chunks
        await self._chunks.delete_many({"document_id": oid})

        # Remove document record
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
