"""
Unit tests for RAGService — Diagno-Pilot
Validates: Requirements REQ-04
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.document import RAGResponse
from backend.services.embedding_service import EmbeddingModel
from backend.services.llm_router import LLMResult, LLMRouter
from backend.services.rag_service import RAGService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(
    doc_id: str = "doc1",
    content: str = "Amoxicillin is a broad-spectrum antibiotic.",
    source: str = "CHU_LOME",
    section: str = "Antibiotics",
    page: int = 1,
) -> dict:
    return {
        "document_id": doc_id,
        "content": content,
        "metadata": {"source": source, "section": section, "page": page},
        "score": 0.95,
    }


def _make_rag_service(chunks: list[dict], llm_answer: str = "Use amoxicillin 50 mg/kg.") -> RAGService:
    """Build a RAGService with fully mocked dependencies."""
    # Mock MongoDB cursor
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=chunks)

    mock_collection = MagicMock()
    mock_collection.aggregate = MagicMock(return_value=mock_cursor)

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_mongo = MagicMock()
    mock_mongo.__getitem__ = MagicMock(return_value=mock_db)

    embedder = MagicMock(spec=EmbeddingModel)
    embedder.encode = AsyncMock(return_value=[0.1] * 1536)

    llm = MagicMock(spec=LLMRouter)
    llm.generate = AsyncMock(return_value=LLMResult(answer=llm_answer, fallback_used=False))
    llm.last_used = "qwen3"

    service = RAGService(mongo_client=mock_mongo, llm_router=llm, embedder=embedder)
    service._chunks = mock_collection
    return service


# ---------------------------------------------------------------------------
# 1. $vectorSearch pipeline construction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRAGServicePipeline:
    async def test_aggregate_called_with_vector_search_stage(self):
        """aggregate() must be called with a $vectorSearch stage."""
        chunks = [_make_chunk()]
        service = _make_rag_service(chunks)

        await service.query("What antibiotic for pneumonia?")

        service._chunks.aggregate.assert_called_once()
        pipeline = service._chunks.aggregate.call_args.args[0]
        assert pipeline[0].get("$vectorSearch") is not None

    async def test_vector_search_uses_correct_index_and_path(self):
        """$vectorSearch must reference the correct index name and embedding path."""
        service = _make_rag_service([])

        await service.query("fever treatment")

        pipeline = service._chunks.aggregate.call_args.args[0]
        vs = pipeline[0]["$vectorSearch"]
        assert vs["index"] == RAGService.VECTOR_INDEX
        assert vs["path"] == "embedding"

    async def test_vector_search_uses_encoded_query_vector(self):
        """The queryVector in $vectorSearch must match the embedder output."""
        expected_vector = [0.42] * 1536
        service = _make_rag_service([])
        service._embedder.encode = AsyncMock(return_value=expected_vector)

        await service.query("malaria symptoms")

        pipeline = service._chunks.aggregate.call_args.args[0]
        vs = pipeline[0]["$vectorSearch"]
        assert vs["queryVector"] == expected_vector

    async def test_top_k_controls_limit(self):
        """The limit in $vectorSearch must equal top_k."""
        service = _make_rag_service([])

        await service.query("cholera treatment", top_k=3)

        pipeline = service._chunks.aggregate.call_args.args[0]
        vs = pipeline[0]["$vectorSearch"]
        assert vs["limit"] == 3

    async def test_num_candidates_is_ten_times_top_k(self):
        """numCandidates must be top_k * 10 for good recall."""
        service = _make_rag_service([])

        await service.query("meningitis", top_k=7)

        pipeline = service._chunks.aggregate.call_args.args[0]
        vs = pipeline[0]["$vectorSearch"]
        assert vs["numCandidates"] == 70


# ---------------------------------------------------------------------------
# 2. Source citation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRAGServiceSources:
    async def test_sources_populated_from_chunks(self):
        """Each retrieved chunk must produce a DocumentSource in the response."""
        chunks = [
            _make_chunk(doc_id="d1", source="CHU_LOME", section="Antibiotics"),
            _make_chunk(doc_id="d2", source="OMS_AFRO", section="Pediatrics"),
        ]
        service = _make_rag_service(chunks)

        response = await service.query("antibiotic dosing")

        assert len(response.sources) == 2
        assert response.sources[0].document_id == "d1"
        assert response.sources[1].document_id == "d2"

    async def test_source_fields_mapped_correctly(self):
        """DocumentSource fields must map from chunk metadata."""
        chunk = _make_chunk(doc_id="doc42", source="MSF", section="Lassa", page=5)
        service = _make_rag_service([chunk])

        response = await service.query("lassa fever")

        src = response.sources[0]
        assert src.document_id == "doc42"
        assert src.source == "MSF"
        assert src.section == "Lassa"
        assert src.page == 5

    async def test_excerpt_truncated_to_200_chars(self):
        """Excerpt must be at most 200 characters."""
        long_content = "x" * 500
        chunk = _make_chunk(content=long_content)
        service = _make_rag_service([chunk])

        response = await service.query("test")

        assert len(response.sources[0].excerpt) <= 200

    async def test_empty_chunks_returns_empty_sources(self):
        """When no chunks are retrieved, sources list must be empty."""
        service = _make_rag_service([])

        response = await service.query("unknown disease")

        assert response.sources == []


# ---------------------------------------------------------------------------
# 3. LLM integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRAGServiceLLM:
    async def test_llm_answer_returned_in_response(self):
        """The LLM answer must appear in the RAGResponse."""
        service = _make_rag_service([], llm_answer="Take amoxicillin 500 mg TID.")

        response = await service.query("antibiotic for strep throat")

        assert response.answer == "Take amoxicillin 500 mg TID."

    async def test_llm_used_field_reflects_router_last_used(self):
        """llm_used in RAGResponse must match LLMRouter.last_used."""
        service = _make_rag_service([])
        service._llm.last_used = "gpt5"

        response = await service.query("test")

        assert response.llm_used == "gpt5"

    async def test_llm_called_with_question_as_prompt(self):
        """LLMRouter.generate must be called with the original question as prompt."""
        service = _make_rag_service([])

        question = "What is the first-line treatment for malaria?"
        await service.query(question)

        call_args = service._llm.generate.call_args
        assert call_args.args[0] == question

    async def test_chunks_passed_as_context_to_llm(self):
        """Retrieved chunk content must be included in the LLM context."""
        chunk = _make_chunk(content="Artemisinin is used for malaria.")
        service = _make_rag_service([chunk])

        await service.query("malaria treatment")

        call_args = service._llm.generate.call_args
        context = call_args.args[1]
        contents = [c.get("content", "") for c in context]
        assert any("Artemisinin" in c for c in contents)

    async def test_returns_rag_response_instance(self):
        """query() must return a RAGResponse instance."""
        service = _make_rag_service([])

        response = await service.query("test query")

        assert isinstance(response, RAGResponse)
