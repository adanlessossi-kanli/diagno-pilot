"""
RAG cache integration tests — Diagno-Pilot

Feature: caching-and-performance

Property 5: RAG response cache round-trip
**Validates: Requirements 5.2, 5.3, 5.4**
"""
from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest
from hypothesis import assume, given, settings as h_settings
from hypothesis import strategies as st

from backend.core.cache import CacheService, cache_service
from backend.core.config import Settings
from backend.models.document import DocumentSource, RAGResponse
from backend.models.patient import PatientProfile
from backend.services.embedding_service import EmbeddingModel
from backend.services.llm_router import LLMRouter
from backend.services.rag_service import RAGService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache_service() -> tuple[CacheService, fakeredis.FakeAsyncRedis]:
    """Return a CacheService wired to a FakeAsyncRedis instance."""
    svc = CacheService(Settings())
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    svc._client = fake
    svc._degraded = False
    return svc, fake


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def _st_document_source() -> st.SearchStrategy[DocumentSource]:
    return st.builds(
        DocumentSource,
        document_id=st.text(min_size=1),
        title=st.text(min_size=1),
        source=st.text(min_size=1),
        section=st.one_of(st.none(), st.text()),
        excerpt=st.one_of(st.none(), st.text()),
        page=st.one_of(st.none(), st.integers(min_value=1, max_value=10_000)),
    )


def _st_rag_response() -> st.SearchStrategy[RAGResponse]:
    return st.builds(
        RAGResponse,
        answer=st.text(min_size=1),
        sources=st.lists(_st_document_source(), min_size=0, max_size=10),
        llm_used=st.text(min_size=1),
        confidence=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
    )


# ---------------------------------------------------------------------------
# Property 5 — RAG response cache round-trip
# ---------------------------------------------------------------------------

# Feature: caching-and-performance, Property 5: RAG response cache round-trip
# Validates: Requirements 5.2, 5.3, 5.4

@given(response=_st_rag_response())
@h_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_p5_rag_response_cache_round_trip(response: RAGResponse):
    """Store RAGResponse in cache, retrieve and deserialise, assert equal to original."""
    cache_svc, fake = _make_cache_service()
    try:
        key = cache_svc.make_key("rag", "testhash")
        await cache_svc.set(key, response.model_dump_json(), ttl=300)
        raw = await cache_svc.get(key)
        assert raw is not None
        restored = RAGResponse.model_validate_json(raw)
        assert restored == response
    finally:
        await fake.aclose()


# ---------------------------------------------------------------------------
# Property 8 — Patient context key isolation
# ---------------------------------------------------------------------------


def _st_patient_profile() -> st.SearchStrategy[PatientProfile]:
    return st.builds(
        PatientProfile,
        id=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        full_name=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
        weight_kg=st.one_of(st.none(), st.floats(min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False)),
        allergies=st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=5),
        current_medications=st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=5),
    )


def _rag_cache_key(question: str, context: PatientProfile | None) -> str:
    q_hash = hashlib.sha256(question.encode()).hexdigest()
    if context is not None:
        ctx_hash = hashlib.sha256(context.model_dump_json().encode()).hexdigest()
        identifier = f"{q_hash}:{ctx_hash}"
    else:
        identifier = q_hash
    return cache_service.make_key("rag", identifier)


# Feature: caching-and-performance, Property 8: patient context key isolation
# Validates: Requirements 5.7

@given(
    question=st.text(min_size=1),
    p1=_st_patient_profile(),
    p2=_st_patient_profile(),
)
@h_settings(max_examples=100, deadline=None)
def test_p8_patient_context_key_isolation(question: str, p1: PatientProfile, p2: PatientProfile):
    """Two distinct patients must produce different cache keys for the same question."""
    assume(p1.model_dump_json() != p2.model_dump_json())
    assert _rag_cache_key(question, p1) != _rag_cache_key(question, p2)


# ---------------------------------------------------------------------------
# Unit tests — RAGService cache integration (Task 7.3)
# ---------------------------------------------------------------------------


def _make_rag_service_with_mock_cache(mock_cache, chunks=None, llm_answer="Test answer"):
    if chunks is None:
        chunks = []
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
    from backend.services.llm_router import LLMResult
    llm = MagicMock(spec=LLMRouter)
    llm.generate = AsyncMock(return_value=LLMResult(answer=llm_answer, fallback_used=False))
    llm.last_used = "test-llm"
    service = RAGService(mongo_client=mock_mongo, llm_router=llm, embedder=embedder)
    service._chunks = mock_collection
    return service


@pytest.mark.asyncio
async def test_cache_hit_skips_pipeline():
    """Cache hit: pipeline (aggregate) must NOT be called; cached response is returned."""
    cached_response = RAGResponse(answer="cached answer", sources=[], llm_used="cached-llm")

    mock_cache = MagicMock()
    mock_cache.is_degraded = False
    mock_cache.get = AsyncMock(return_value=cached_response.model_dump_json())
    mock_cache.make_key = MagicMock(return_value="v1:rag:abc123")

    service = _make_rag_service_with_mock_cache(mock_cache)

    with patch("backend.services.rag_service.cache_service", mock_cache):
        result = await service.query("What antibiotic for pneumonia?")

    service._chunks.aggregate.assert_not_called()
    assert result.answer == "cached answer"
    assert result.llm_used == "cached-llm"


@pytest.mark.asyncio
async def test_cache_miss_executes_pipeline_and_stores_result():
    """Cache miss: pipeline IS executed and cache.set() is called with correct key prefix."""
    mock_cache = MagicMock()
    mock_cache.is_degraded = False
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    mock_cache.make_key = MagicMock(side_effect=lambda domain, identifier: f"v1:{domain}:{identifier}")

    service = _make_rag_service_with_mock_cache(mock_cache, llm_answer="Pipeline answer")

    with patch("backend.services.rag_service.cache_service", mock_cache):
        await service.query("fever treatment")

    service._chunks.aggregate.assert_called_once()
    mock_cache.set.assert_called_once()
    set_key = mock_cache.set.call_args[0][0]
    assert set_key.startswith("v1:rag:")
    set_value = mock_cache.set.call_args[0][1]
    restored = RAGResponse.model_validate_json(set_value)
    assert restored.answer == "Pipeline answer"


@pytest.mark.asyncio
async def test_degraded_mode_executes_pipeline_without_error():
    """Degraded mode: full pipeline executes and returns a valid RAGResponse without raising."""
    mock_cache = MagicMock()
    mock_cache.is_degraded = True
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    mock_cache.make_key = MagicMock(side_effect=lambda domain, identifier: f"v1:{domain}:{identifier}")

    service = _make_rag_service_with_mock_cache(mock_cache, llm_answer="Degraded answer")

    with patch("backend.services.rag_service.cache_service", mock_cache):
        result = await service.query("malaria treatment")

    assert isinstance(result, RAGResponse)
    assert result.answer == "Degraded answer"
    service._chunks.aggregate.assert_called_once()


@pytest.mark.asyncio
async def test_patient_context_produces_different_keys_for_different_patients():
    """Two distinct PatientProfile objects must produce different cache keys."""
    captured_keys: list[str] = []

    async def _capture_set(key, value, ttl):
        captured_keys.append(key)

    mock_cache = MagicMock()
    mock_cache.is_degraded = False
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock(side_effect=_capture_set)
    mock_cache.make_key = MagicMock(side_effect=lambda domain, identifier: f"v1:{domain}:{identifier}")

    patient_a = PatientProfile(id="patient-001")
    patient_b = PatientProfile(id="patient-002")

    question = "What is the dosage for amoxicillin?"

    service_a = _make_rag_service_with_mock_cache(mock_cache)
    service_b = _make_rag_service_with_mock_cache(mock_cache)

    with patch("backend.services.rag_service.cache_service", mock_cache):
        await service_a.query(question, context=patient_a)
        await service_b.query(question, context=patient_b)

    assert len(captured_keys) == 2
    assert captured_keys[0] != captured_keys[1]
