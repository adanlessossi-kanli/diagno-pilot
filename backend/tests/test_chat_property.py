"""
Tests de propriété pour ChatService — Diagno-Pilot

**Validates: Requirements REQ-04**

Propriété 8 : Toute réponse du chat RAG contient au moins une source citée
(document + section).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.document import DocumentSource
from backend.models.patient import PatientProfile
from backend.services.chat_service import ChatService
from backend.services.llamaindex_pipeline import StreamEvent

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

message_strategy = st.text(min_size=1, max_size=200).filter(str.strip)

source_strategy = st.builds(
    DocumentSource,
    document_id=st.uuids().map(str),
    title=st.text(min_size=1, max_size=80).filter(str.strip),
    source=st.sampled_from(["CHU_LOME", "OMS_AFRO", "MSF", "PNLP", "CHU_ABOMEY"]),
    section=st.one_of(
        st.none(),
        st.text(min_size=1, max_size=50).filter(str.strip),
    ),
    excerpt=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
    page=st.one_of(st.none(), st.integers(min_value=1, max_value=500)),
)

sources_strategy = st.lists(source_strategy, min_size=1, max_size=5)

patient_context_strategy = st.one_of(
    st.none(),
    st.builds(
        PatientProfile,
        full_name=st.text(min_size=1, max_size=50).filter(str.strip),
        date_of_birth=st.none(),
        weight_kg=st.one_of(st.none(), st.floats(min_value=1.0, max_value=200.0, allow_nan=False)),
        age_group=st.none(),
        allergies=st.lists(st.text(min_size=1, max_size=20), max_size=3),
        current_medications=st.lists(st.text(min_size=1, max_size=20), max_size=3),
    ),
)

answer_strategy = st.text(min_size=1, max_size=500).filter(str.strip)


# ---------------------------------------------------------------------------
# Property 8 : every RAG chat response contains at least one cited source
# ---------------------------------------------------------------------------

@given(
    message=message_strategy,
    sources=sources_strategy,
    answer=answer_strategy,
    patient_context=patient_context_strategy,
)
@h_settings(max_examples=100)
def test_chat_response_always_contains_at_least_one_source(
    message: str,
    sources: list[DocumentSource],
    answer: str,
    patient_context: PatientProfile | None,
):
    """
    **Validates: Requirements REQ-04**

    For any user message, ChatService.send_message_stream must yield a done
    StreamEvent that contains at least one DocumentSource with a non-empty
    document_id and a non-empty source field.
    """
    # Build a mock RAGService that yields streaming events
    async def _fake_query_stream(**kwargs):
        yield StreamEvent(type="token", content=answer)
        yield StreamEvent(
            type="done",
            answer=answer,
            sources=sources,
            llm_used="mock",
        )

    mock_rag = MagicMock()
    mock_rag.query_stream = MagicMock(side_effect=_fake_query_stream)

    # Build a mock DB that accepts upserts without hitting MongoDB
    mock_db = MagicMock()
    mock_collection = AsyncMock()
    mock_collection.update_one = AsyncMock(return_value=None)
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    service = ChatService(db=mock_db, rag_service=mock_rag)

    async def _collect():
        done_event = None
        async for event in service.send_message_stream(
            session_id=None,
            user_message=message,
            patient_context=patient_context,
        ):
            if event.type == "done":
                done_event = event
        return done_event

    done_event = asyncio.run(_collect())

    assert done_event is not None, "Expected a done event from send_message_stream"

    # Property: at least one source must be present
    assert len(done_event.sources) >= 1, (
        f"Expected at least 1 source in done event, got {len(done_event.sources)}"
    )

    for src in done_event.sources:
        # Each source must have a non-empty document_id
        assert src.document_id and src.document_id.strip(), (
            f"DocumentSource.document_id must be non-empty, got {src.document_id!r}"
        )
        # Each source must have a non-empty source field
        assert src.source and src.source.strip(), (
            f"DocumentSource.source must be non-empty, got {src.source!r}"
        )
