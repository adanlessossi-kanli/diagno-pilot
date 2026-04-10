"""
LlamaIndexPipeline — unified RAG pipeline replacing RAGService.

Combines IndexManager retrieval with LLMRouter generation, Redis caching
(embeddings 24 h, RAG responses 5 min), and a grounding system prompt.

Implements Requirements 4.7, 4.8.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

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
# Streaming data class
# ---------------------------------------------------------------------------


@dataclass
class StreamEvent:
    """Event yielded by the RAG pipeline and ChatService streaming methods."""
    type: str  # "token" | "done" | "error"
    content: str | None = None
    answer: str | None = None
    sources: list[DocumentSource] | None = None
    llm_used: str | None = None
    fallback_used: bool = False
    confidence_score: float | None = None
    error: str | None = None
    retryable: bool = False


# ---------------------------------------------------------------------------
# Grounding constants (shared with legacy RAGService for consistency)
# ---------------------------------------------------------------------------

NO_CONTEXT_MESSAGE = "Information non disponible dans la base de connaissances."

GROUNDING_SYSTEM_PROMPT = (
    "Tu es un assistant médical spécialisé en maladies tropicales et médecine générale. "
    "Détecte la langue du message de l'utilisateur et réponds dans cette même langue. "
    "En cas d'ambiguïté (mot unique, texte mixte), utilise la langue de la locale fournie. "
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
        cache_key = self._build_cache_key(question, context, region, session_history=session_history)
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

        # --- Check collection size for degraded warning (O(1) on MongoDB) ---
        degraded_warning: str | None = None
        try:
            doc_count = await self._index._collection.estimated_document_count()
            if doc_count == 0:
                degraded_warning = (
                    "No medical documents indexed — diagnoses are based on "
                    "LLM general knowledge only."
                )
        except Exception as exc:
            logger.warning("estimated_document_count() failed: %s", exc)

        # --- No chunks: still call LLM with medical knowledge ---
        if not chunks:
            if degraded_warning is None:
                degraded_warning = (
                    "No relevant documents found for these symptoms — diagnoses "
                    "are based on LLM general knowledge only."
                )

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
                degraded_warning=degraded_warning,
            )
            await cache_service.set(
                cache_key, response.model_dump_json(), ttl=settings.CACHE_TTL_RAG
            )
            return response

        # --- Build unified top_chunks (sorted by ce_score when available, else score) ---
        top_chunks = sorted(
            chunks,
            key=lambda c: float(c.get("ce_score", c.get("score", 0.0))),
            reverse=True,
        )[:min(top_k, 5)]
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
                confidence_score=float(c.get("ce_score", c.get("score", 0.0))),
            )
            for c in top_chunks
        ]

        # Req 10.1–10.4: Filter sources by relevance threshold
        source_threshold = settings.SOURCE_RELEVANCE_THRESHOLD
        sources = [
            s for s, c in zip(sources, top_chunks)
            if float(c.get("ce_score", c.get("score", 0.0))) >= source_threshold
        ]

        # --- Build LLM context ---
        llm_context_with_chunks: list[dict[str, str]] = [
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
                    llm_context_with_chunks.append({"role": role, "content": content})
        if context:
            llm_context_with_chunks.append(
                {"role": "system", "content": f"Patient context: {context.model_dump_json()}"}
            )
        for c in top_chunks[:3]:
            llm_context_with_chunks.append({"role": "system", "content": c.get("content", "")[:300]})

        # --- Generate answer ---
        llm_result = await self._llm.generate(question, llm_context_with_chunks)

        # --- Confidence score (mean of source chunk scores) ---
        source_scores: list[float] = [
            float(c.get("ce_score", c.get("score", 0.0))) for c in top_chunks
        ]
        confidence_score: float | None = (
            (sum(source_scores) / len(source_scores)) if source_scores else None
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

    async def query_stream(
        self,
        question: str,
        context: PatientProfile | None = None,
        top_k: int = 5,
        region: str | None = None,
        source_filter: dict[str, Any] | None = None,
        session_history: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream tokens from the LLM after retrieval, yielding StreamEvents.

        Same retrieval and context-building logic as ``query()``, but streams
        tokens incrementally via ``LLMRouter.generate_stream()``.  A terminal
        ``done`` or ``error`` event is always emitted last.

        Requirements: 3.1, 3.2, 3.3, 3.4.
        """
        # --- Cache lookup ---
        cache_key = self._build_cache_key(
            question, context, region, session_history=session_history
        )
        cached = await cache_service.get(cache_key)
        if cached is not None:
            cache_hits_total.labels(cache="rag").inc()
            cached_response = RAGResponse.model_validate_json(cached)
            yield StreamEvent(type="token", content=cached_response.answer)
            yield StreamEvent(
                type="done",
                answer=cached_response.answer,
                sources=cached_response.sources,
                llm_used=cached_response.llm_used,
                fallback_used=cached_response.fallback_used,
                confidence_score=cached_response.confidence_score,
            )
            return
        cache_misses_total.labels(cache="rag").inc()

        # --- Embed the query and retrieve chunks ---
        try:
            query_vector = await self._embedder.encode(question)
            chunks = await self._index.retrieve(
                query_vector,
                question,
                top_k=top_k,
                region=region,
                source_filter=source_filter,
            )
        except Exception as exc:
            logger.error("Retrieval failed during query_stream: %s", exc)
            yield StreamEvent(
                type="error",
                error=f"Retrieval failed: {exc}",
                retryable=True,
            )
            return

        # --- Build sources and LLM context ---
        sources: list[DocumentSource] = []
        confidence_score: float | None = None

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
        else:
            top_chunks = sorted(
                chunks,
                key=lambda c: float(c.get("ce_score", c.get("score", 0.0))),
                reverse=True,
            )[:min(top_k, 5)]
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
                    confidence_score=float(c.get("ce_score", c.get("score", 0.0))),
                )
                for c in top_chunks
            ]
            source_threshold = settings.SOURCE_RELEVANCE_THRESHOLD
            sources = [
                s for s, c in zip(sources, top_chunks)
                if float(c.get("ce_score", c.get("score", 0.0))) >= source_threshold
            ]

            source_scores: list[float] = [
                float(c.get("ce_score", c.get("score", 0.0))) for c in top_chunks
            ]
            confidence_score = (
                (sum(source_scores) / len(source_scores)) if source_scores else None
            )

            llm_context = [
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
            for c in top_chunks[:3]:
                llm_context.append({"role": "system", "content": c.get("content", "")[:300]})

        # --- Stream tokens from LLMRouter ---
        accumulated = ""
        fallback_used = False
        llm_used = "unknown"

        try:
            async for chunk in self._llm.generate_stream(question, llm_context):
                if chunk.error is not None:
                    yield StreamEvent(
                        type="error",
                        error=chunk.error,
                        retryable=False,
                    )
                    return
                if chunk.token is not None:
                    accumulated += chunk.token
                    fallback_used = chunk.fallback_used
                    llm_used = chunk.llm_used
                    yield StreamEvent(type="token", content=chunk.token)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
            yield StreamEvent(
                type="error",
                error=detail.get("error", str(exc.detail)),
                retryable=bool(detail.get("retryable", True)),
            )
            return

        # --- Cache the assembled response ---
        response = RAGResponse(
            answer=accumulated,
            sources=sources,
            llm_used=llm_used,
            fallback_used=fallback_used,
            confidence_score=confidence_score,
        )
        await cache_service.set(
            cache_key, response.model_dump_json(), ttl=settings.CACHE_TTL_RAG
        )

        # --- Terminal done event ---
        yield StreamEvent(
            type="done",
            answer=accumulated,
            sources=sources,
            llm_used=llm_used,
            fallback_used=fallback_used,
            confidence_score=confidence_score,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_cache_key(
        question: str,
        context: PatientProfile | None,
        region: str | None,
        session_history: list[dict[str, Any]] | None = None,
    ) -> str:
        q_hash = hashlib.sha256(question.encode()).hexdigest()
        if context is not None:
            ctx_hash = hashlib.sha256(context.model_dump_json().encode()).hexdigest()
            identifier = f"{q_hash}:{ctx_hash}"
        else:
            identifier = q_hash
        if region and region != "ALL":
            identifier = f"{identifier}:region={region}"
        if session_history:
            history_str = json.dumps(session_history, sort_keys=True, default=str)
            h_hash = hashlib.sha256(history_str.encode()).hexdigest()
            identifier = f"{identifier}:hist={h_hash}"
        return cache_service.make_key("rag", identifier)
