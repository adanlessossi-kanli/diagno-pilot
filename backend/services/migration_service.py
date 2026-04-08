"""
ChunkMigrationService — re-indexes existing document chunks using the LlamaIndex pipeline.

Iterates medical_documents → fetches raw file from S3 → loads via SourceLoaderService →
chunks via SemanticChunkerService → embeds and inserts via IndexManager → deletes old
chunks → updates chunk_count.

Implements Requirements 14.1–14.7.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.core.db_metrics import timed_db_op
from backend.services.embedding_model import EmbeddingModel
from backend.services.index_manager import IndexManager
from backend.services.s3_service import S3Service
from backend.services.semantic_chunker import SemanticChunkerService
from backend.services.source_loaders import SourceLoaderService

logger = logging.getLogger(__name__)

# Reuse disease keywords and infer_document_type from document_service
from backend.services.document_service import DISEASE_KEYWORDS, infer_document_type  # noqa: E402


@dataclass
class MigrationResult:
    """Result for a single document migration."""
    document_id: str
    title: str
    success: bool
    old_chunk_count: int = 0
    new_chunk_count: int = 0
    error: str | None = None


@dataclass
class MigrationReport:
    """Aggregate report for a full migration run."""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[MigrationResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


class ChunkMigrationService:
    """Re-indexes existing document_chunks using the LlamaIndex pipeline.

    Designed to be run as a one-time admin command (POST /api/v1/admin/migrate-chunks)
    or via CLI script. NOT triggered automatically on startup.

    Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        s3: S3Service,
        source_loader: SourceLoaderService | None = None,
        semantic_chunker: SemanticChunkerService | None = None,
        index_manager: IndexManager | None = None,
        embedder: EmbeddingModel | None = None,
    ) -> None:
        self._db = db
        self._docs = db["medical_documents"]
        self._chunks = db["document_chunks"]
        self._s3 = s3
        self._source_loader = source_loader or SourceLoaderService()
        self._semantic_chunker = semantic_chunker or SemanticChunkerService()
        self._index_manager = index_manager or IndexManager(db=db)
        self._embedder = embedder or EmbeddingModel()

    async def migrate_all(self) -> MigrationReport:
        """Re-index all documents. Returns report with success/failure counts.

        Continues on per-document failure (Requirement 14.6).
        """
        report = MigrationReport()

        async with timed_db_op("medical_documents", "find"):
            cursor = self._docs.find({})
            documents = await cursor.to_list(length=None)

        report.total = len(documents)
        logger.info("Migration started: %d document(s) to process.", report.total)

        for doc in documents:
            doc_id = str(doc["_id"])
            title = doc.get("title", "unknown")
            result = await self._migrate_one(doc)
            report.results.append(result)
            if result.success:
                report.succeeded += 1
                logger.info(
                    "Migrated '%s' (%s): %d → %d chunks",
                    title, doc_id, result.old_chunk_count, result.new_chunk_count,
                )
            else:
                report.failed += 1
                logger.error(
                    "Migration failed for '%s' (%s): %s",
                    title, doc_id, result.error,
                )

        report.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Migration complete: %d/%d succeeded, %d failed.",
            report.succeeded, report.total, report.failed,
        )
        return report

    async def migrate_document(self, doc_id: str) -> MigrationResult:
        """Re-index a single document by its ID."""
        try:
            oid = ObjectId(doc_id)
        except Exception:
            return MigrationResult(
                document_id=doc_id, title="unknown", success=False,
                error=f"Invalid document ID: {doc_id}",
            )

        async with timed_db_op("medical_documents", "find_one"):
            doc = await self._docs.find_one({"_id": oid})

        if doc is None:
            return MigrationResult(
                document_id=doc_id, title="unknown", success=False,
                error=f"Document not found: {doc_id}",
            )

        return await self._migrate_one(doc)

    async def _migrate_one(self, doc: dict[str, Any]) -> MigrationResult:
        """Internal: migrate a single document dict."""
        doc_id = str(doc["_id"])
        title = doc.get("title", "unknown")
        s3_key = doc.get("s3_key")
        source = doc.get("source", "")
        old_chunk_count = doc.get("chunk_count", 0)

        if not s3_key:
            return MigrationResult(
                document_id=doc_id, title=title, success=False,
                old_chunk_count=old_chunk_count,
                error="No s3_key on document record — cannot fetch source file.",
            )

        try:
            # 1. Fetch raw file from S3
            content = await self._s3.download(s3_key)

            # 2. Infer filename from s3_key
            filename = s3_key.rsplit("/", 1)[-1] if "/" in s3_key else s3_key
            # Strip UUID prefix if present (format: {uuid}_{original_name})
            if "_" in filename:
                filename = filename.split("_", 1)[1]

            # 3. Detect region from existing chunks metadata (preserve, Req 14.2)
            region = await self._detect_region(doc["_id"])

            # 4. Load via SourceLoaderService
            documents = self._source_loader.load(content, filename, source, region)

            # 5. Chunk via SemanticChunkerService
            nodes = self._semantic_chunker.chunk(documents)

            # 6. Embed and build chunk records
            new_count = await self._embed_and_insert(
                nodes, doc["_id"], source, region,
            )

            # 7. Delete old chunks (Req 14.4)
            await self._delete_old_chunks(doc["_id"])

            # 8. Update chunk_count on medical_documents record (Req 14.5)
            async with timed_db_op("medical_documents", "update_one"):
                await self._docs.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"chunk_count": new_count}},
                )

            return MigrationResult(
                document_id=doc_id, title=title, success=True,
                old_chunk_count=old_chunk_count, new_chunk_count=new_count,
            )

        except Exception as exc:
            logger.exception("Error migrating document %s", doc_id)
            return MigrationResult(
                document_id=doc_id, title=title, success=False,
                old_chunk_count=old_chunk_count,
                error=str(exc),
            )

    async def _detect_region(self, doc_oid: ObjectId) -> str:
        """Read region from existing chunks for this document, default to ALL."""
        async with timed_db_op("document_chunks", "find_one"):
            chunk = await self._chunks.find_one(
                {"document_id": doc_oid},
                {"metadata.region": 1},
            )
        if chunk and chunk.get("metadata", {}).get("region"):
            return chunk["metadata"]["region"]
        return "ALL"

    async def _embed_and_insert(
        self,
        nodes: list,
        doc_oid: ObjectId,
        source: str,
        region: str,
    ) -> int:
        """Embed each TextNode and insert via IndexManager. Returns count."""
        if not nodes:
            return 0

        document_type = infer_document_type(source)
        evidence_level = document_type
        records: list[dict[str, Any]] = []

        for node in nodes:
            embedding = await self._embedder.encode(node.text)
            content_lower = node.text.lower()
            disease_tags = [kw for kw in DISEASE_KEYWORDS if kw in content_lower]

            node_meta = dict(node.metadata) if node.metadata else {}
            metadata: dict[str, Any] = {
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

            records.append({
                "_id": ObjectId(),
                "document_id": doc_oid,
                "content": node.text,
                "embedding": embedding,
                "metadata": metadata,
            })

        if records:
            return await self._index_manager.insert_nodes(records)
        return 0

    async def _delete_old_chunks(self, doc_oid: ObjectId) -> int:
        """Delete all existing chunks for a document. Returns deleted count."""
        async with timed_db_op("document_chunks", "delete_many"):
            result = await self._chunks.delete_many({"document_id": doc_oid})
        return result.deleted_count
