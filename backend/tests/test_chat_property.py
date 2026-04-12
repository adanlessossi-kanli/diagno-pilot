"""
Tests de propriété pour ChatService — Diagno-Pilot

**Validates: Requirements 1.4 (assistant-qa-and-documents-redesign)**

Propriété : Toute réponse du chat Q&A (LLM-only, sans RAG) contient
un tableau de sources vide (`sources: []`).

Note: L'ancienne propriété 8 (au moins une source citée) s'applique
désormais au DocumentChatService (RAG), pas au ChatService Q&A.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.patient import PatientProfile
from backend.services.chat_service import ChatService
from backend.services.llm_router import StreamChunk

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

message_strategy = st.text(min_size=1, max_size=200).filter(str.strip)

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
# Property: Q&A chat always returns empty sources (LLM-only, no RAG)
# ---------------------------------------------------------------------------

@given(
    message=message_strategy,
    answer=answer_strategy,
    patient_context=patient_context_strategy,
)
@h_settings(max_examples=100)
def test_chat_response_always_contains_empty_sources(
    message: str,
    answer: str,
    patient_context: PatientProfile | None,
):
    """
    **Validates: Requirements 1.4**

    For any user message, ChatService.send_message_stream must yield a done
    StreamEvent that contains an empty sources array, since the Q&A chat
    no longer uses RAG.
    """
    mock_llm = MagicMock()

    async def _fake_generate_stream(prompt: str, context: list[dict]):
        for word in answer.split():
            yield StreamChunk(token=word + " ", llm_used="mock")

    mock_llm.generate_stream = _fake_generate_stream

    mock_db = MagicMock()
    mock_collection = AsyncMock()
    mock_collection.update_one = AsyncMock(return_value=None)
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    service = ChatService(db=mock_db, llm_router=mock_llm)

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

    # Property: sources must be empty (LLM-only, no RAG)
    assert done_event.sources == [], (
        f"Expected empty sources in done event, got {done_event.sources!r}"
    )
