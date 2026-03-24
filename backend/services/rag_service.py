"""RAGService — retrieval-augmented generation over MongoDB Atlas Vector Search."""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient

from backend.models.document import DocumentSource, RAGResponse
from backend.models.patient import PatientProfile
from backend.services.embedding_service import EmbeddingModel
from backend.services.llm_router import LLMRouter


class RAGService:
    """Encodes a query, retrieves top-k chunks via $vectorSearch, then generates an answer."""

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
        """Retrieve relevant chunks and generate a grounded answer."""
        query_vector = await self._embedder.encode(question)

        pipeline = [
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

        chunks = await self._chunks.aggregate(pipeline).to_list(top_k)

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
            llm_context.append({"role": "system", "content": f"Patient context: {context.model_dump()}"})
        for c in chunks:
            llm_context.append({"role": "system", "content": c.get("content", "")})

        answer = await self._llm.generate(question, llm_context)

        return RAGResponse(
            answer=answer,
            sources=sources,
            llm_used=self._llm.last_used or "unknown",
        )
