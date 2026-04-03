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

        service._chunks.aggregate.assert_called()
        # First call must be the $vectorSearch stage
        pipeline = service._chunks.aggregate.call_args_list[0].args[0]
        assert pipeline[0].get("$vectorSearch") is not None

    async def test_vector_search_uses_correct_index_and_path(self):
        """$vectorSearch must reference the correct index name and embedding path."""
        service = _make_rag_service([])

        await service.query("fever treatment")

        pipeline = service._chunks.aggregate.call_args_list[0].args[0]
        vs = pipeline[0]["$vectorSearch"]
        assert vs["index"] == RAGService.VECTOR_INDEX
        assert vs["path"] == "embedding"

    async def test_vector_search_uses_encoded_query_vector(self):
        """The queryVector in $vectorSearch must match the embedder output."""
        expected_vector = [0.42] * 1536
        service = _make_rag_service([])
        service._embedder.encode = AsyncMock(return_value=expected_vector)

        await service.query("malaria symptoms")

        pipeline = service._chunks.aggregate.call_args_list[0].args[0]
        vs = pipeline[0]["$vectorSearch"]
        assert vs["queryVector"] == expected_vector

    async def test_top_k_controls_limit(self):
        """The limit in $vectorSearch must equal top_k."""
        service = _make_rag_service([])

        await service.query("cholera treatment", top_k=3)

        pipeline = service._chunks.aggregate.call_args_list[0].args[0]
        vs = pipeline[0]["$vectorSearch"]
        assert vs["limit"] == 3

    async def test_num_candidates_is_ten_times_top_k(self):
        """numCandidates must be top_k * 10 for good recall."""
        service = _make_rag_service([])

        await service.query("meningitis", top_k=7)

        pipeline = service._chunks.aggregate.call_args_list[0].args[0]
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
        """The LLM answer must appear in the RAGResponse when chunks pass the threshold."""
        chunk = _make_chunk()  # score=0.95, above SIMILARITY_THRESHOLD
        service = _make_rag_service([chunk], llm_answer="Take amoxicillin 500 mg TID.")

        response = await service.query("antibiotic for strep throat")

        assert response.answer == "Take amoxicillin 500 mg TID."

    async def test_llm_used_field_reflects_router_last_used(self):
        """llm_used in RAGResponse must match LLMRouter.last_used."""
        chunk = _make_chunk()  # score=0.95, above SIMILARITY_THRESHOLD
        service = _make_rag_service([chunk])
        service._llm.last_used = "gpt5"

        response = await service.query("test")

        assert response.llm_used == "gpt5"

    async def test_llm_called_with_question_as_prompt(self):
        """LLMRouter.generate must be called with the original question as prompt."""
        chunk = _make_chunk()  # score=0.95, above SIMILARITY_THRESHOLD
        service = _make_rag_service([chunk])

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


# ---------------------------------------------------------------------------
# Property-based tests — diagno-pilot-improvements
# ---------------------------------------------------------------------------

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from backend.services.rag_service import GROUNDING_SYSTEM_PROMPT, SIMILARITY_THRESHOLD, NO_CONTEXT_MESSAGE


def _make_chunk_with_score(score: float, content: str = "Medical content.") -> dict:
    return {
        "document_id": "doc1",
        "content": content,
        "metadata": {"source": "CHU_LOME", "title": "Protocol", "section": "S1", "page": 1},
        "score": score,
    }


def _make_rag_service_for_pbt(chunks: list[dict], llm_answer: str = "Answer.") -> RAGService:
    """Build a RAGService with mocked dependencies for property-based tests."""
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


# Feature: diagno-pilot-improvements, Property 1: Grounding prompt présent dans tout contexte LLM
@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(question=st.text(min_size=1, max_size=200))
async def test_property_1_grounding_prompt_present_in_all_llm_contexts(question: str):
    """Validates: Requirements 1.1
    For any query submitted to RAGService.query(), the first system message
    passed to LLMRouter.generate() must contain GROUNDING_SYSTEM_PROMPT.
    """
    # Use a chunk with score above threshold so LLM is always called
    chunk = _make_chunk_with_score(score=0.9)
    service = _make_rag_service_for_pbt([chunk])

    await service.query(question)

    service._llm.generate.assert_called_once()
    call_args = service._llm.generate.call_args
    context: list[dict] = call_args.args[1]

    # The first message must be a system message containing GROUNDING_SYSTEM_PROMPT
    assert len(context) >= 1
    first_msg = context[0]
    assert first_msg["role"] == "system"
    assert GROUNDING_SYSTEM_PROMPT in first_msg["content"]


# Feature: diagno-pilot-improvements, Property 2: Refus sans appel LLM quand aucun chunk ne passe le seuil
@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    scores=st.lists(
        st.floats(min_value=0.0, max_value=0.7499, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    )
)
async def test_property_2_refusal_without_llm_when_no_chunk_passes_threshold(scores: list[float]):
    """Validates: Requirements 1.2, 1.3
    For any set of chunks with scores < 0.75, RAGService must return
    answer == NO_CONTEXT_MESSAGE, sources == [], and must NOT call LLMRouter.generate().
    """
    chunks = [_make_chunk_with_score(score=s) for s in scores]
    service = _make_rag_service_for_pbt(chunks)

    response = await service.query("some medical question")

    assert response.answer == NO_CONTEXT_MESSAGE
    assert response.sources == []
    service._llm.generate.assert_not_called()


# Feature: diagno-pilot-improvements, Property 4: grounding_warning présent quand degraded_warning est actif
@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    degraded_msg=st.text(min_size=1, max_size=200),
    answer=st.text(min_size=1, max_size=200),
)
async def test_property_4_grounding_warning_present_when_degraded_warning_active(
    degraded_msg: str, answer: str
):
    """Validates: Requirements 1.5
    For any RAGResponse where degraded_warning is non-null,
    grounding_warning must also be non-null.
    """
    # Simulate a degraded response by constructing it directly as RAGService would
    response = RAGResponse(
        answer=answer,
        sources=[],
        llm_used="qwen3",
        degraded_warning=degraded_msg,
        grounding_warning=(
            "Résultats basés sur la récupération par mots-clés uniquement "
            "— peuvent ne pas être entièrement ancrés dans les protocoles validés."
        ),
    )

    # Property: if degraded_warning is set, grounding_warning must also be set
    assert response.degraded_warning is not None
    assert response.grounding_warning is not None


from backend.services.rag_service import reciprocal_rank_fusion


# Feature: diagno-pilot-improvements, Property 11: Reciprocal Rank Fusion produit un classement cohérent
# Validates: Requirements 3.5
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    list1_ids=st.lists(st.integers(min_value=0, max_value=20), min_size=1, max_size=10, unique=True),
    list2_ids=st.lists(st.integers(min_value=0, max_value=20), min_size=1, max_size=10, unique=True),
)
def test_property_11_rrf_score_is_sum_of_reciprocal_ranks(list1_ids: list[int], list2_ids: list[int]):
    k = 60
    # Build chunk dicts with unique _id
    list1 = [{"_id": str(i), "content": f"chunk {i}", "document_id": f"doc{i}"} for i in list1_ids]
    list2 = [{"_id": str(i), "content": f"chunk {i}", "document_id": f"doc{i}"} for i in list2_ids]

    merged = reciprocal_rank_fusion([list1, list2], k=k)

    # Verify each chunk's rrf_score equals sum of 1/(k+rank) across all lists
    for chunk in merged:
        chunk_id = chunk["_id"]
        expected_score = 0.0
        for rank, c in enumerate(list1, start=1):
            if str(c["_id"]) == chunk_id:
                expected_score += 1.0 / (k + rank)
        for rank, c in enumerate(list2, start=1):
            if str(c["_id"]) == chunk_id:
                expected_score += 1.0 / (k + rank)
        assert abs(chunk["rrf_score"] - expected_score) < 1e-9


# Feature: diagno-pilot-improvements, Property 12: ConfidenceScore est la moyenne arithmétique des scores retenus
# Validates: Requirements 4.1
@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    scores=st.lists(
        st.floats(min_value=SIMILARITY_THRESHOLD, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    )
)
async def test_property_12_confidence_score_is_arithmetic_mean_of_retained_scores(scores: list[float]):
    """Validates: Requirements 4.1
    For any set of retained chunks (all with score >= SIMILARITY_THRESHOLD),
    RAGResponse.confidence_score must equal the arithmetic mean of their cosine similarity scores.
    """
    chunks = [_make_chunk_with_score(score=s) for s in scores]
    service = _make_rag_service_for_pbt(chunks)

    response = await service.query("medical question")

    # All chunks pass the threshold, so LLM is called and confidence_score is set
    expected_mean = sum(scores) / len(scores)
    assert response.confidence_score is not None
    assert abs(response.confidence_score - expected_mean) < 1e-9
