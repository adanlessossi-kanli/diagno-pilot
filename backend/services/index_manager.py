"""
IndexManager — LlamaIndex VectorStoreIndex backed by MongoDB Atlas.

Manages index creation, incremental node insertion, hybrid retrieval
(vector + BM25 via QueryFusionRetriever), similarity post-processing,
cross-encoder re-ranking, and region-based pre-filtering.

Implements Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6.
"""
from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VECTOR_INDEX_NAME = "embedding_index"
COLLECTION_NAME = "document_chunks"


# ---------------------------------------------------------------------------
# Similarity post-processor (pure function, no LlamaIndex dependency)
# ---------------------------------------------------------------------------


def filter_by_similarity(
    chunks: list[dict[str, Any]],
    threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Return only chunks whose ``score`` >= *threshold*.

    Chunks without a ``score`` key are retained (e.g. BM25 results).
    Implements Requirement 4.4.
    """
    threshold = threshold if threshold is not None else settings.LLAMAINDEX_SIMILARITY_THRESHOLD
    return [c for c in chunks if c.get("ce_score", c.get("score", 1.0)) >= threshold]


def filter_by_region(
    chunks: list[dict[str, Any]],
    region: str | None,
) -> list[dict[str, Any]]:
    """Return only chunks whose region matches *region* or is ``"ALL"``.

    When *region* is ``None`` or ``"ALL"``, all chunks pass.
    Implements Requirement 4.6.
    """
    if not region or region == "ALL":
        return list(chunks)
    return [
        c for c in chunks
        if c.get("metadata", {}).get("region", "ALL") in (region, "ALL")
    ]


# ---------------------------------------------------------------------------
# BM25 retriever (keyword search over MongoDB text index)
# ---------------------------------------------------------------------------


class BM25Retriever:
    """Simple BM25 keyword retrieval over the document_chunks collection."""

    def __init__(self, collection: Any) -> None:
        self._collection = collection

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        region: str | None = None,
        source_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to *top_k* chunks matching *query* via MongoDB ``$text`` search."""
        match_stage: dict[str, Any] = {"$text": {"$search": query}}
        if region and region != "ALL":
            match_stage["metadata.region"] = {"$in": [region, "ALL"]}
        if source_filter:
            match_stage.update(source_filter)

        pipeline: list[dict[str, Any]] = [
            {"$match": match_stage},
            {"$limit": top_k},
            {"$project": {"content": 1, "metadata": 1, "document_id": 1}},
        ]
        try:
            return await self._collection.aggregate(pipeline).to_list(top_k)
        except Exception as exc:
            logger.warning("BM25 retrieval failed: %s", exc)
            return []


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    k: int = 60,
) -> list[dict[str, Any]]:
    """Merge N ranked lists via RRF.  score = Σ 1/(k + rank)."""
    scores: dict[str, float] = {}
    chunks_by_id: dict[str, dict[str, Any]] = {}
    for ranked_list in ranked_lists:
        for rank, chunk in enumerate(ranked_list, start=1):
            chunk_id = str(
                chunk.get("_id", str(chunk.get("document_id", "")) + str(rank))
            )
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            chunks_by_id[chunk_id] = chunk
    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    result: list[dict[str, Any]] = []
    for cid in sorted_ids:
        chunk = dict(chunks_by_id[cid])
        chunk["rrf_score"] = scores[cid]
        result.append(chunk)
    return result


# ---------------------------------------------------------------------------
# Cross-encoder re-ranker (best-effort)
# ---------------------------------------------------------------------------


def cross_encoder_rerank(
    query: str,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Re-rank *chunks* using a cross-encoder model.  Falls back to identity on error."""
    if not chunks:
        return chunks
    try:
        from backend.services.document_service import get_cross_encoder

        cross_encoder = get_cross_encoder()
        pairs = [(query, c.get("content", "")) for c in chunks]
        ce_scores = cross_encoder.predict(pairs)
        for score, chunk in zip(ce_scores, chunks):
            chunk["ce_score"] = float(score)
        return sorted(chunks, key=lambda c: c["ce_score"], reverse=True)
    except Exception:
        logger.debug("Cross-encoder unavailable — skipping re-rank.")
        return chunks


# ---------------------------------------------------------------------------
# IndexManager
# ---------------------------------------------------------------------------


class IndexManager:
    """Creates and maintains a vector store index over MongoDB Atlas.

    Provides hybrid retrieval (vector + BM25 via RRF), similarity filtering,
    cross-encoder re-ranking, and region-based pre-filtering.

    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6.
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        collection_name: str = COLLECTION_NAME,
        vector_index_name: str = VECTOR_INDEX_NAME,
    ) -> None:
        self._db = db
        self._collection_name = collection_name
        self._vector_index_name = vector_index_name
        self._collection = db[collection_name]
        self._bm25 = BM25Retriever(self._collection)

    # ------------------------------------------------------------------
    # Node insertion (incremental — Req 4.5)
    # ------------------------------------------------------------------

    async def insert_nodes(self, nodes: list[dict[str, Any]]) -> int:
        """Insert LlamaIndex nodes (as dicts) into MongoDB.

        Each dict should contain at minimum: ``content``, ``embedding``,
        ``metadata``, and ``document_id``.

        Returns the number of inserted documents.
        """
        if not nodes:
            return 0
        from backend.core.db_metrics import timed_db_op

        async with timed_db_op(self._collection_name, "insert_many"):
            result = await self._collection.insert_many(nodes)
        count = len(result.inserted_ids)
        logger.info("Inserted %d nodes into '%s'.", count, self._collection_name)
        return count

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        query_vector: list[float],
        query_text: str,
        *,
        top_k: int = 5,
        region: str | None = None,
        source_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid retrieval: vector search + BM25, fused via RRF.

        1. MongoDB Atlas ``$vectorSearch`` with optional region pre-filter.
        2. BM25 keyword search.
        3. Reciprocal Rank Fusion to merge both lists.
        4. Cross-encoder re-ranking (best-effort).
        5. Similarity threshold filtering.

        Returns a list of chunk dicts sorted by relevance.
        """
        from backend.core.db_metrics import timed_db_op

        # --- Vector search stage ---
        vector_search_stage: dict[str, Any] = {
            "index": self._vector_index_name,
            "path": "embedding",
            "queryVector": query_vector,
            "numCandidates": top_k * 10,
            "limit": top_k,
        }

        # Region pre-filter (Req 4.6)
        pre_filter: dict[str, Any] = {}
        if region and region != "ALL":
            pre_filter["metadata.region"] = {"$in": [region, "ALL"]}
        if source_filter:
            pre_filter.update(source_filter)
        if pre_filter:
            vector_search_stage["filter"] = pre_filter

        pipeline: list[dict[str, Any]] = [
            {"$vectorSearch": vector_search_stage},
            {
                "$project": {
                    "content": 1,
                    "metadata": 1,
                    "document_id": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]

        vector_chunks: list[dict[str, Any]] = []
        try:
            async with timed_db_op(self._collection_name, "aggregate"):
                vector_chunks = await self._collection.aggregate(pipeline).to_list(top_k)
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)

        # --- BM25 keyword search ---
        bm25_chunks = await self._bm25.retrieve(query_text, top_k=top_k, region=region, source_filter=source_filter)

        # --- Fusion ---
        if vector_chunks and bm25_chunks:
            chunks = reciprocal_rank_fusion([vector_chunks, bm25_chunks], k=60)
        elif vector_chunks:
            chunks = vector_chunks
        elif bm25_chunks:
            chunks = bm25_chunks
        else:
            chunks = []

        # --- Cross-encoder re-ranking (Req 4.3) ---
        chunks = cross_encoder_rerank(query_text, chunks)

        # --- Similarity threshold filter (Req 4.4) ---
        chunks = filter_by_similarity(chunks)

        return chunks

    # ------------------------------------------------------------------
    # Deletion helpers (for migration / re-indexing)
    # ------------------------------------------------------------------

    async def delete_by_document_id(self, document_id: str) -> int:
        """Delete all chunks for a given document_id.  Returns deleted count."""
        from backend.core.db_metrics import timed_db_op

        async with timed_db_op(self._collection_name, "delete_many"):
            result = await self._collection.delete_many({"document_id": document_id})
        return result.deleted_count
