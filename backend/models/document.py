from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HighlightInfo(BaseModel):
    """Bounding box and page information for highlighting a passage in a PDF.

    Requirements: 5.2
    """
    bbox: list[float]  # [x0, y0, x1, y1] in PDF user-space coordinates
    page: int          # 0-based page number


class DocumentSource(BaseModel):
    document_id: str
    title: str        # populated from metadata.title
    source: str       # populated from metadata.source (organisation)
    section: str | None = None
    excerpt: str | None = None
    page: int | None = None
    highlight: HighlightInfo | None = None  # populated from metadata.bbox + metadata.page (REQ 5.2)
    confidence_score: float | None = None


class MedicalDocument(BaseModel):
    id: str | None = None
    title: str
    source: str
    s3_key: str | None = None
    indexed_at: datetime | None = None
    chunk_count: int = 0
    created_at: datetime | None = None


class ChunkMetadata(BaseModel):
    """Metadata attached to each LlamaIndex TextNode stored in MongoDB.

    Requirements: 2.6, 3.7
    """
    source: str
    page: int | None = None
    section: str | None = None
    region: str = "ALL"
    disease_tags: list[str] = []
    document_type: str = "other"  # protocol | guideline | other
    evidence_level: str = "other"
    bbox: list[float] | None = None
    page_char_start: int | None = None
    page_char_end: int | None = None
    title: str | None = None


class ChunkNode(BaseModel):
    """Represents a LlamaIndex TextNode stored in MongoDB.

    Requirements: 2.6, 3.7
    """
    id: str
    document_id: str
    content: str
    embedding: list[float]
    metadata: ChunkMetadata


class RAGResponse(BaseModel):
    answer: str
    sources: list[DocumentSource]
    llm_used: str
    confidence: float | None = None
    confidence_score: float | None = None  # arithmetic mean of retained chunk scores
    degraded_warning: str | None = None
    grounding_warning: str | None = None   # set when degraded_warning is active
    fallback_used: bool = False
