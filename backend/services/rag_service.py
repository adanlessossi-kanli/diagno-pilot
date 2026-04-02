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


class RAGService:
    """Retrieval-augmented generation service for medical knowledge queries.

    Implements the RAG pipeline in three stages:
    1. **Embedding** — the query string is encoded into a dense vector via
       :class:`EmbeddingModel`.
    2. **Vector search** — the vector is used to retrieve the most relevant
       document chunks from MongoDB Atlas using the ``$vectorSearch`` aggregation
       stage against the ``embedding_index`` index on the ``document_chunks``
       collection.
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
    ) -> None:
        self._db = mongo_client[db_name]
        self._chunks = self._db[self.COLLECTION]
        self._llm = llm_router
        self._embedder = embedder

    async def query(
        self,
        question: str,
        context: PatientProfile | None = None,
        top_k: int = 5,
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
        pipeline: list[dict[str, Any]] = [
            {
                "$vectorSearch": {
                    "index": self.VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": top_k * 10,
                    "limit": top_k,
                }
            },
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

        sources = [
            DocumentSource(
                document_id=str(c.get("document_id", "")),
                title=c.get("metadata", {}).get("source", ""),
                source=c.get("metadata", {}).get("source", ""),
                section=c.get("metadata", {}).get("section"),
                excerpt=c.get("content", "")[:200],
                page=c.get("metadata", {}).get("page"),
            )
            for c in chunks
        ]

        # Build LLM context from retrieved passages
        llm_context: list[dict] = []
        if context:
            llm_context.append({"role": "system", "content": f"Patient context: {context.model_dump_json()}"})
        for c in chunks:
            llm_context.append({"role": "system", "content": c.get("content", "")})

        llm_result = await self._llm.generate(question, llm_context)

        response = RAGResponse(
            answer=llm_result.answer,
            sources=sources,
            llm_used=self._llm.last_used or "unknown",
            fallback_used=llm_result.fallback_used,
            degraded_warning=degraded_warning,
        )

        await cache_service.set(key, response.model_dump_json(), ttl=settings.CACHE_TTL_RAG)
        return response
