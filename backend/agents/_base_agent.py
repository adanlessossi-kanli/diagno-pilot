"""Base logic shared by all specialist diagnostic agents.

Each agent script reads a JSON request from stdin, calls RAGService.query()
with a source_filter applied to the $vectorSearch pipeline, then writes a
JSON response to stdout.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from backend.core.config import settings
from backend.models.patient import PatientProfile
from backend.services.embedding_service import EmbeddingModel
from backend.services.llm_router import LLMRouter
from backend.services.rag_service import RAGService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Partial-differential extraction helpers
# ---------------------------------------------------------------------------
_CONDITION_RE = re.compile(
    r"(?:diagnostic|pathologie|condition|maladie)\s*[:\-–]\s*([^\n,;]+)",
    re.IGNORECASE,
)
_ICD_RE = re.compile(r"\b([A-Z]\d{2}(?:\.\d+)?)\b")


def _parse_partial_differential(answer: str) -> list[dict[str, Any]]:
    """Extract a partial differential list from the LLM answer text.

    Returns a list of dicts compatible with DifferentialDiagnosis.
    Falls back to an empty list when nothing can be parsed.
    """
    results: list[dict[str, Any]] = []
    for match in _CONDITION_RE.finditer(answer):
        condition = match.group(1).strip().rstrip(".")
        icd_match = _ICD_RE.search(answer[match.start():match.start() + 120])
        results.append(
            {
                "condition": condition,
                "probability": 0.5,
                "icd_code": icd_match.group(1) if icd_match else None,
                "matching_symptoms": [],
            }
        )
    return results


# ---------------------------------------------------------------------------
# Filtered RAGService subclass
# ---------------------------------------------------------------------------
class FilteredRAGService(RAGService):
    """RAGService subclass that injects a MongoDB pre-filter into $vectorSearch."""

    def __init__(self, source_filter: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._source_filter = source_filter

    async def query(self, question: str, context: PatientProfile | None = None,
                    top_k: int = 5, region: str | None = None):  # type: ignore[override]
        """Override to merge source_filter into the $vectorSearch filter."""
        # Temporarily patch the pipeline by monkey-patching the parent's
        # vector_search_stage construction.  We do this by calling the parent
        # and then re-running with the filter injected.
        #
        # Simpler approach: build the pipeline directly here.
        import hashlib
        from typing import Any as _Any

        from backend.core.cache import cache_service
        from backend.core.metrics import cache_hits_total, cache_misses_total
        from backend.core.db_metrics import timed_db_op
        from backend.models.document import DocumentSource, RAGResponse
        from backend.services.rag_service import (
            GROUNDING_SYSTEM_PROMPT,
            NO_CONTEXT_MESSAGE,
            SIMILARITY_THRESHOLD,
        )

        # Cache key
        q_hash = hashlib.sha256(question.encode()).hexdigest()
        if context is not None:
            ctx_hash = hashlib.sha256(context.model_dump_json().encode()).hexdigest()
            identifier = f"{q_hash}:{ctx_hash}"
        else:
            identifier = q_hash
        filter_hash = hashlib.sha256(json.dumps(self._source_filter, sort_keys=True).encode()).hexdigest()[:8]
        identifier = f"{identifier}:sf={filter_hash}"
        if region and region != "ALL":
            identifier = f"{identifier}:region={region}"
        key = cache_service.make_key("rag", identifier)

        cached = await cache_service.get(key)
        if cached is not None:
            cache_hits_total.labels(cache="rag").inc()
            return RAGResponse.model_validate_json(cached)
        cache_misses_total.labels(cache="rag").inc()

        query_vector = await self._embedder.encode(question)

        # Build combined filter: source_filter AND optional region filter
        combined_filter: dict[str, _Any] = dict(self._source_filter)
        if region and region != "ALL":
            combined_filter["metadata.region"] = {"$in": [region, "ALL"]}

        vector_search_stage: dict[str, _Any] = {
            "index": self.VECTOR_INDEX,
            "path": "embedding",
            "queryVector": query_vector,
            "numCandidates": top_k * 10,
            "limit": top_k,
            "filter": combined_filter,
        }

        pipeline: list[dict[str, _Any]] = [
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

        chunks: list[dict[str, _Any]] = []
        degraded_warning: str | None = None
        try:
            async with timed_db_op(self.COLLECTION, "aggregate"):
                chunks = await self._chunks.aggregate(pipeline).to_list(top_k)
        except Exception as exc:
            logger.warning("FilteredRAGService vector search failed: %s", exc)
            chunks = []
            degraded_warning = "Vector Search unavailable — response generated without document context"

        if not degraded_warning:
            chunks = [c for c in chunks if c.get("score", 0.0) >= SIMILARITY_THRESHOLD]

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

        llm_context: list[dict] = [{"role": "system", "content": GROUNDING_SYSTEM_PROMPT}]
        if context:
            llm_context.append({"role": "system", "content": f"Patient context: {context.model_dump_json()}"})
        for c in chunks:
            llm_context.append({"role": "system", "content": c.get("content", "")})

        llm_result = await self._llm.generate(question, llm_context)

        scores = [c.get("score", 0.0) for c in chunks if c.get("score") is not None]
        confidence_score: float | None = (sum(scores) / len(scores)) if scores else None

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


# ---------------------------------------------------------------------------
# Main entry point used by each agent script
# ---------------------------------------------------------------------------
async def run_agent(source_filter: dict[str, Any]) -> None:
    """Read stdin, run RAG with source_filter, write JSON to stdout."""
    raw = sys.stdin.read()
    request: dict[str, Any] = json.loads(raw)

    sub_question: str = request["sub_question"]
    patient_data: dict | None = request.get("patient_profile")
    locale: str = request.get("locale", "fr-TG")
    region: str | None = request.get("region")

    patient_profile: PatientProfile | None = None
    if patient_data:
        try:
            patient_profile = PatientProfile(**patient_data)
        except Exception:
            patient_profile = None

    mongo_client = AsyncIOMotorClient(settings.MONGODB_URI)
    llm_router = LLMRouter()
    embedder = EmbeddingModel()

    rag = FilteredRAGService(
        source_filter=source_filter,
        mongo_client=mongo_client,
        llm_router=llm_router,
        embedder=embedder,
    )

    response = await rag.query(sub_question, context=patient_profile, region=region)

    chunks = [
        {
            "document_id": s.document_id,
            "title": s.title,
            "source": s.source,
            "excerpt": s.excerpt,
            "page": s.page,
        }
        for s in response.sources
    ]

    partial_differential = _parse_partial_differential(response.answer)

    result = {
        "chunks": chunks,
        "confidence_score": response.confidence_score or 0.0,
        "partial_differential": partial_differential,
    }

    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()
    mongo_client.close()
