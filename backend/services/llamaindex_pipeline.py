"""
LlamaIndexPipeline — unified RAG pipeline replacing RAGService.

Combines IndexManager retrieval with LLMRouter generation, Redis caching
(embeddings 24 h, RAG responses 5 min), and a grounding system prompt.

Implements Requirements 4.7, 4.8.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from backend.core.cache import cache_service
from backend.core.config import settings
from backend.core.metrics import cache_hits_total, cache_misses_total
from backend.models.document import DocumentSource, RAGResponse
from backend.models.patient import PatientProfile
from backend.services.embedding_model import EmbeddingModel
from backend.services.index_manager import IndexManager
from backend.services.llm_router import LLMRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Grounding constants (shared with legacy RAGService for consistency)
# ---------------------------------------------------------------------------

NO_CONTEXT_MESSAGE = "Information non disponible dans la base de connaissances."

GROUNDING_SYSTEM_PROMPT = (
    "Tu es un assistant médical spécialisé en maladies tropicales et médecine générale. "
    "Réponds en priorité en te basant sur les passages de documents fournis ci-dessous. "
    "Si les passages fournis ne contiennent pas d'information pertinente, tu peux utiliser "
    "tes connaissances médicales pour répondre, mais uniquement pour des questions médicales "
    "et cliniques. Précise alors que la réponse provient de tes connaissances générales. "
    "Refuse poliment toute question non médicale."
)


def _truncate_excerpt(text: str, max_chars: int = 500) -> str:
    """Truncate *text* at a sentence boundary up to *max_chars*."""
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    for sep in (". ", ".\n", ".\t"):
        idx = window.rfind(sep)
        if idx > max_chars // 2:
            return window[: idx + 1].rstrip()
    idx = window.rfind(" ")
    if idx > 0:
        return window[:idx] + "…"
    return window + "…"


# ---------------------------------------------------------------------------
# LlamaIndexPipeline
# ---------------------------------------------------------------------------


class LlamaIndexPipeline:
    """LlamaIndex-based RAG pipeline replacing RAGService.

    Dependencies:
        - IndexManager: hybrid retrieval over MongoDB Atlas.
        - LLMRouter: primary (Model_Container) + fallback (GPT-5).
        - EmbeddingModel: query vector generation.
        - CacheService (module-level singleton): Redis caching.

    Requirements: 4.7, 4.8.
    """

    def __init__(
        self,
        index_manager: IndexManager,
        llm_router: LLMRouter,
        embedder: EmbeddingModel,
    ) -> None:
        self._index = index_manager
        self._llm = llm_router
        self._embedder = embedder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(
        self,
        question: str,
        context: PatientProfile | None = None,
        top_k: int = 5,
        region: str | None = None,
        source_filter: dict[str, Any] | None = None,
        session_history: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> RAGResponse:
        """Retrieve relevant chunks and generate a grounded answer.

        Args:
            question: Natural-language query.
            context: Optional patient profile for personalisation.
            top_k: Number of chunks to retrieve.
            region: Region pre-filter (``"TG"``, ``"BJ"``, ``"ALL"``).
            source_filter: Additional MongoDB metadata filters per agent.
            session_history: Last N chat messages for conversational context.
            system_prompt: Override the default grounding prompt.

        Returns:
            A ``RAGResponse`` with answer, sources, llm_used, confidence, etc.
        """
        # --- Cache lookup (RAG responses: 5 min TTL) ---
        cache_key = self._build_cache_key(question, context, region)
        cached = await cache_service.get(cache_key)
        if cached is not None:
            cache_hits_total.labels(cache="rag").inc()
            return RAGResponse.model_validate_json(cached)
        cache_misses_total.labels(cache="rag").inc()

        # --- Embed the query ---
        query_vector = await self._embedder.encode(question)

        # --- Retrieve chunks via IndexManager (hybrid) ---
        chunks = await self._index.retrieve(
            query_vector,
            question,
            top_k=top_k,
            region=region,
            source_filter=source_filter,
        )

        # --- No chunks: still call LLM with medical knowledge ---
        if not chunks:
            llm_context: list[dict[str, str]] = [
                {
                    "role": "system",
                    "content": system_prompt
                    if system_prompt is not None
                    else GROUNDING_SYSTEM_PROMPT,
                },
            ]
            if session_history:
                for msg in session_history:
                    role = msg.get("role", "user")
                    content_val = msg.get("content", "")
                    if role in ("user", "assistant") and content_val:
                        llm_context.append({"role": role, "content": content_val})
            if context:
                llm_context.append(
                    {"role": "system", "content": f"Patient context: {context.model_dump_json()}"}
                )

            llm_result = await self._llm.generate(question, llm_context)

            response = RAGResponse(
                answer=llm_result.answer,
                sources=[],
                llm_used=self._llm.last_used or "unknown",
                fallback_used=llm_result.fallback_used,
                confidence_score=None,
            )
            await cache_service.set(
                cache_key, response.model_dump_json(), ttl=settings.CACHE_TTL_RAG
            )
            return response

        # --- Build sources (top 5 most relevant only) ---
        top_chunks = sorted(
            chunks,
            key=lambda c: float(c.get("score", 0.0)),
            reverse=True,
        )[:5]
        sources = [
            DocumentSource(
                document_id=str(c.get("document_id", "")),
                title=c.get("metadata", {}).get(
                    "title", c.get("metadata", {}).get("source", "")
                ),
                source=c.get("metadata", {}).get("source", ""),
                section=c.get("metadata", {}).get("section"),
                excerpt=_truncate_excerpt(c.get("content", "")),
                page=c.get("metadata", {}).get("page"),
            )
            for c in top_chunks
        ]

        # --- Build LLM context ---
        llm_context: list[dict[str, str]] = [
            {
                "role": "system",
                "content": system_prompt
                if system_prompt is not None
                else GROUNDING_SYSTEM_PROMPT,
            },
        ]
        if session_history:
            for msg in session_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    llm_context.append({"role": role, "content": content})
        if context:
            llm_context.append(
                {"role": "system", "content": f"Patient context: {context.model_dump_json()}"}
            )
        for c in chunks[:3]:
            llm_context.append({"role": "system", "content": c.get("content", "")[:300]})

        # --- Generate answer ---
        llm_result = await self._llm.generate(question, llm_context)

        # --- Confidence score (arithmetic mean of cosine scores) ---
        cosine_scores: list[float] = [
            float(c["score"]) for c in chunks if c.get("score") is not None
        ]
        confidence_score: float | None = (
            (sum(cosine_scores) / len(cosine_scores)) if cosine_scores else None
        )

        response = RAGResponse(
            answer=llm_result.answer,
            sources=sources,
            llm_used=self._llm.last_used or "unknown",
            fallback_used=llm_result.fallback_used,
            confidence_score=confidence_score,
        )

        await cache_service.set(
            cache_key, response.model_dump_json(), ttl=settings.CACHE_TTL_RAG
        )
        return response

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_cache_key(
        question: str,
        context: PatientProfile | None,
        region: str | None,
    ) -> str:
        q_hash = hashlib.sha256(question.encode()).hexdigest()
        if context is not None:
            ctx_hash = hashlib.sha256(context.model_dump_json().encode()).hexdigest()
            identifier = f"{q_hash}:{ctx_hash}"
        else:
            identifier = q_hash
        if region and region != "ALL":
            identifier = f"{identifier}:region={region}"
        return cache_service.make_key("rag", identifier)
