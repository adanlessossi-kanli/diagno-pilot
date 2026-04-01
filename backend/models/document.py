from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentSource(BaseModel):
    document_id: str
    title: str
    source: str
    section: str | None = None
    excerpt: str | None = None
    page: int | None = None


class MedicalDocument(BaseModel):
    id: str | None = None
    title: str
    source: str
    s3_key: str | None = None
    indexed_at: datetime | None = None
    chunk_count: int = 0
    created_at: datetime | None = None


class RAGResponse(BaseModel):
    answer: str
    sources: list[DocumentSource]
    llm_used: str
    confidence: float | None = None
    degraded_warning: str | None = None
    fallback_used: bool = False
