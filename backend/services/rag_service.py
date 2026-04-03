"""RAGService — retrieval-augmented generation over MongoDB Atlas Vector Search."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from backend.core.cache import cache_service
from backend.core.metrics import cache_hits_total, cache_misses_total
from backend.core.config import settings
from backend.core.db_metrics import timed_db_op
from backend.models.document import DocumentSource, RAGResponse
from backend.models.patient import PatientProfile
from backend.services.embedding_service import EmbeddingModel
from backend.services.llm_router import LLMRouter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion — REQ 3.5
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(ranked_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """Merge N ranked lists via RRF. score = sum(1 / (k + rank)) for each chunk across all lists."""
    scores: dict[str, float] = {}
    chunks_by_id: dict[str, dict] = {}
    for ranked_list in ranked_lists:
        for rank, chunk in enumerate(ranked_list, start=1):
            chunk_id = str(chunk.get("_id", chunk.get("document_id", "") + str(rank)))
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            chunks_by_id[chunk_id] = chunk
    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    result = []
    for cid in sorted_ids:
        chunk = dict(chunks_by_id[cid])
        chunk["rrf_score"] = scores[cid]
        result.append(chunk)
    return result


# ---------------------------------------------------------------------------
# BM25 Retriever — REQ 3.4
# ---------------------------------------------------------------------------

class BM25_Retriever:
    """Simple BM25 keyword retrieval over MongoDB document_chunks collection."""

    def __init__(self, collection) -> None:
        self._collection = collection

    async def retrieve(self, query: str, top_k: int = 5, region: str | None = None) -> list[dict]:
        """Retrieve chunks using $text search (BM25-like keyword matching)."""
        match_filter: dict = {"$text": {"$search": query}}
        if region and region != "ALL":
            match_filter["metadata.region"] = {"$in": [region, "ALL"]}
        try:
            pipeline = [
                {"$match": match_filter},
                {"$addFields": {"score": {"$meta": "textScore"}}},
                {"$sort": {"score": -1}},
                {"$limit": top_k},
            ]
            async with timed_db_op("document_chunks", "aggregate"):
                return await self._collection.aggregate(pipeline).to_list(top_k)
        except Exception:
            return []

# ---------------------------------------------------------------------------
# Grounding constants — REQ 1.1, 1.2, 1.3
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.75
NO_CONTEXT_MESSAGE = "Information non disponible dans la base de connaissances."

GROUNDING_SYSTEM_PROMPT = (
    "Tu es un assistant médical. Réponds UNIQUEMENT en te basant sur les passages "
    "de documents fournis ci-dessous. Si aucun passage pertinent n'est disponible, "
    'réponds exactement : "' + NO_CONTEXT_MESSAGE + '". '
    "N'utilise jamais tes connaissances paramétriques."
)


class RAGService:
    """Retrieval-augmented generation service for medical knowledge queries.

    Implements the RAG pipeline in three stages:
    1. **Embedding** — the query string is encoded into a dense vector via
       :class:`EmbeddingModel`.
    2. **Hybrid retrieval** — vector search + BM25 results are merged via
       Reciprocal Rank Fusion, then re-ranked by CrossEncoder.
    3. **LLM generation** — the retrieved passages (and optional patient context)
       are forwarded to :class:`LLMRouter`, which produces a grounded natural-
       language answer.

    MongoDB details:
        - Collection: ``document_chunks`` (see :attr:`COLLECTION`)
        - Vector index: ``embedding_index`` (see :attr:`VECTOR_INDEX`)
        - Database: ``diagno_pilot`` (configurable via the ``db_name`` constructor
          argument)

    Indexed medical document sources:
        - **CHU Lomé / CHU Abomey-Calavi** — clinical protocols from the teaching
          hospitals of Togo and Benin.
        - **OMS AFRO** — WHO Regional Office for Africa guidelines.
        - **MSF** — Médecins Sans Frontières clinical guidelines.
        - **PNLP** — Programme National de Lutte contre le Paludisme (national
          malaria-control programme) treatment protocols.
    """

    COLLECTION = "document_chunks"
    VECTOR_INDEX = "embedding_index"

    def __init__(
        self,
        mongo_client: AsyncIOMotorClient,
        llm_router: LLMRouter,
        embedder: EmbeddingModel,
        db_name: str = "diagno_pilot",
        bm25_retriever: BM25_Retriever | None = None,
    ) -> None:
        self._db = mongo_client[db_name]
        self._chunks = self._db[self.COLLECTION]
        self._llm = llm_router
        self._embedder = embedder
        self._bm25 = bm25_retriever or BM25_Retriever(self._chunks)

    async def query(
        self,
        question: str,
        context: PatientProfile | None = None,
        top_k: int = 5,
        region: str | None = None,
        session_history: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> RAGResponse:
        """Retrieve relevant document chunks and generate a grounded answer.

        Args:
            question: The natural-language query to answer (e.g. a clinical
                question or symptom description).
            context: Optional patient profile.  When provided, a ``system``
                message containing the serialised profile is prepended to the
                LLM context so that the generated answer can be personalised
                (e.g. adjusted for paediatric weight, renal failure, known
                allergies).
            top_k: Number of document chunks to retrieve from the vector index.
                Higher values increase recall at the cost of a larger LLM
                context window.  Defaults to ``5``.
            region: Optional ISO 3166-1 alpha-2 region code (e.g. ``"TG"``,
                ``"BJ"``).  When provided and not ``"ALL"``, the
                ``$vectorSearch`` pipeline is extended with a pre-filter that
                restricts results to documents whose ``metadata.region`` is
                either the requested region or ``"ALL"``.  When ``None`` or
                ``"ALL"``, no filter is applied and all documents are eligible.
            session_history: Optional list of the last 5 messages from the chat
                session (user and assistant turns).  When provided, these are
                included in the LLM context after the grounding prompt and
                before the patient context.

        Returns:
            A :class:`~backend.models.document.RAGResponse` with three fields:

            - ``answer`` (*str*) — the LLM-generated response grounded in the
              retrieved passages.
            - ``sources`` (*list[DocumentSource]*) — metadata for each retrieved
              chunk (document ID, title, source organisation, section, page, and
              a 200-character excerpt).
            - ``llm_used`` (*str*) — identifier of the LLM endpoint that
              produced the answer (primary or fallback), as reported by
              :class:`~backend.services.llm_router.LLMRouter`.
        """
        # --- Cache lookup ---
        q_hash = hashlib.sha256(question.encode()).hexdigest()
        if context is not None:
            ctx_hash = hashlib.sha256(context.model_dump_json().encode()).hexdigest()
            identifier = f"{q_hash}:{ctx_hash}"
        else:
            identifier = q_hash
        if region and region != "ALL":
            identifier = f"{identifier}:region={region}"
        key = cache_service.make_key("rag", identifier)

        cached = await cache_service.get(key)
        if cached is not None:
            cache_hits_total.labels(cache="rag").inc()
            return RAGResponse.model_validate_json(cached)

        cache_misses_total.labels(cache="rag").inc()
        # --- End cache lookup ---

        # EmbeddingModel.encode exceptions propagate immediately — no fallback.
        query_vector = await self._embedder.encode(question)

        degraded_warning: str | None = None
        chunks: list[dict[str, Any]] = []

        # --- Vector search (with keyword fallback on failure) ---
        vector_search_stage: dict[str, Any] = {
            "index": self.VECTOR_INDEX,
            "path": "embedding",
            "queryVector": query_vector,
            "numCandidates": top_k * 10,
            "limit": top_k,
        }
        if region and region != "ALL":
            vector_search_stage["filter"] = {
                "metadata.region": {"$in": [region, "ALL"]}
            }

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

        try:
            async with timed_db_op(self.COLLECTION, "aggregate"):
                chunks = await self._chunks.aggregate(pipeline).to_list(top_k)

            # --- Hybrid retrieval: BM25 + RRF — REQ 3.4, 3.5 ---
            bm25_chunks = await self._bm25.retrieve(question, top_k=top_k, region=region)
            if bm25_chunks:
                chunks = reciprocal_rank_fusion([chunks, bm25_chunks], k=60)

            # --- CrossEncoder re-ranking — REQ 3.6 (best-effort) ---
            if chunks:
                try:
                    from backend.services.document_service import get_cross_encoder
                    cross_encoder = get_cross_encoder()
                    pairs = [(question, c.get("content", "")) for c in chunks]
                    ce_scores = cross_encoder.predict(pairs)
                    chunks = [
                        c for _, c in sorted(
                            zip(ce_scores, chunks), key=lambda x: x[0], reverse=True
                        )
                    ]
                except Exception:
                    pass  # CrossEncoder unavailable — skip re-ranking

        except Exception as exc:
            logger.warning(
                "Vector Search failed — attempting keyword fallback. error=%s", exc
            )
            # Keyword fallback: $text search on content field
            try:
                keyword_pipeline: list[dict[str, Any]] = [
                    {"$match": {"$text": {"$search": question}}},
                    {"$limit": top_k},
                ]
                async with timed_db_op(self.COLLECTION, "aggregate"):
                    chunks = await self._chunks.aggregate(keyword_pipeline).to_list(top_k)
            except Exception:
                chunks = []

            if chunks:
                degraded_warning = (
                    "Vector Search unavailable — response based on keyword retrieval only"
                )
            else:
                degraded_warning = (
                    "Vector Search and keyword retrieval unavailable"
                    " — response generated without document context"
                )

        # --- Similarity threshold filter — REQ 1.2, 1.3 ---
        # Discard chunks whose cosine similarity score is below SIMILARITY_THRESHOLD.
        # Chunks from keyword fallback have no score field; they are kept as-is.
        # After RRF, filter on the original cosine 'score' field (not rrf_score).
        if not degraded_warning:
            chunks = [c for c in chunks if c.get("score", 0.0) >= SIMILARITY_THRESHOLD]

        # If no chunks pass the filter, return a structured refusal without calling LLM.
        if not chunks and not degraded_warning:
            refusal = RAGResponse(
                answer=NO_CONTEXT_MESSAGE,
                sources=[],
                llm_used="none",
                confidence_score=0.0,
            )
            await cache_service.set(key, refusal.model_dump_json(), ttl=settings.CACHE_TTL_RAG)
            return refusal

        sources = [
            DocumentSource(
                document_id=str(c.get("document_id", "")),
                title=c.get("metadata", {}).get("title", c.get("metadata", {}).get("source", "")),
                source=c.get("metadata", {}).get("source", ""),
                section=c.get("metadata", {}).get("section"),
                excerpt=c.get("content", "")[:200],
                page=c.get("metadata", {}).get("page"),
            )
            for c in chunks
        ]

        # Build LLM context — grounding prompt is always first — REQ 1.1
        llm_context: list[dict] = [
            {"role": "system", "content": system_prompt if system_prompt is not None else GROUNDING_SYSTEM_PROMPT},
        ]
        # Include session history after grounding prompt — REQ 3.7
        if session_history:
            for msg in session_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    llm_context.append({"role": role, "content": content})
        if context:
            llm_context.append({"role": "system", "content": f"Patient context: {context.model_dump_json()}"})
        for c in chunks:
            llm_context.append({"role": "system", "content": c.get("content", "")})

        llm_result = await self._llm.generate(question, llm_context)

        # Compute confidence_score — arithmetic mean of cosine similarity scores — REQ 4.1
        cosine_scores = [c.get("score") for c in chunks if c.get("score") is not None]
        confidence_score: float | None = (sum(cosine_scores) / len(cosine_scores)) if cosine_scores else None

        # Populate grounding_warning when degraded_warning is active — REQ 1.5
        grounding_warning: str | None = None
        if degraded_warning:
            grounding_warning = (
                "Résultats basés sur la récupération par mots-clés uniquement "
                "— peuvent ne pas être entièrement ancrés dans les protocoles validés."
            )

        response = RAGResponse(
            answer=llm_result.answer,
            sources=sources,
            llm_used=self._llm.last_used or "unknown",
            fallback_used=llm_result.fallback_used,
            degraded_warning=degraded_warning,
            grounding_warning=grounding_warning,
            confidence_score=confidence_score,
        )

        await cache_service.set(key, response.model_dump_json(), ttl=settings.CACHE_TTL_RAG)
        return response
