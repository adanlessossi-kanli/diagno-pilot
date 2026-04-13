"""ChatService — LLM-only medical Q&A assistant with Topic Guard (no RAG)."""
from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.core.db_metrics import timed_db_op
from backend.models.document import DocumentSource
from backend.models.patient import PatientProfile
from backend.services.llamaindex_pipeline import StreamEvent
from backend.services.llm_router import LLMRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — Topic Guard + language detection
# ---------------------------------------------------------------------------

ASSISTANT_QA_SYSTEM_PROMPT = (
    "You are a specialized medical assistant for healthcare professionals in tropical regions. "
    "You answer questions about the following medical domains:\n"
    "- Tropical diseases: malaria, dengue, typhoid fever, yellow fever, chikungunya, "
    "schistosomiasis, filariasis, trypanosomiasis, leishmaniasis, cholera, Ebola, etc.\n"
    "- Infectious diseases: tuberculosis, HIV/AIDS, hepatitis, meningitis, pneumonia, "
    "sexually transmitted infections, parasitic infections, fungal infections, etc.\n"
    "- General clinical medicine: diagnosis, symptoms, treatment protocols, pharmacology, "
    "patient management, emergency medicine, pediatrics, obstetrics, surgery, etc.\n"
    "- Nutrition: malnutrition, dietary recommendations, micronutrient deficiencies, etc.\n"
    "- Mental health: depression, anxiety, PTSD, psychopharmacology, etc.\n"
    "- Medical ethics: informed consent, confidentiality, clinical trial ethics, etc.\n\n"
    "IMPORTANT: If the user's question is about ANY of the above medical topics, "
    "you MUST answer it helpfully and thoroughly. Do NOT refuse medical questions.\n\n"
    "ONLY refuse questions that are clearly non-medical (e.g. sports scores, recipes, "
    "celebrity gossip, politics, video games, travel tips unrelated to health). "
    "When refusing, prefix your response with '[TOPIC_GUARD_REFUSAL]' followed by a line break, "
    "then a polite explanation that you specialize in medical topics.\n\n"
    "Detect the language of the user's message and respond in that same language. "
    "If ambiguous, default to French."
)

# Model-specific markers that may leak into streamed output (e.g. MedicalQwen3
# reasoning tokens).  These are stripped from both individual tokens and the
# final assembled answer before persistence and delivery to the frontend.

_MODEL_MARKER_RE = re.compile(
    r"\[RESEARCH_ANSWER\]"
    r"|\[/RESEARCH_ANSWER\]"
    r"|<\|research_answer\|>"
    r"|<\|/research_answer\|>"
    r"|\[STOP\]"
    r"|<\|stop\|>"
)


def _strip_model_markers(text: str) -> str:
    """Remove model-specific reasoning markers from *text*."""
    return _MODEL_MARKER_RE.sub("", text)


class ChatMessage:
    """In-memory representation of a single chat turn."""

    __slots__ = ("id", "role", "content", "sources", "timestamp")

    def __init__(
        self,
        role: str,
        content: str,
        sources: list[DocumentSource] | None = None,
        message_id: str | None = None,
    ) -> None:
        self.id: str = message_id or str(uuid.uuid4())
        self.role: str = role  # 'user' | 'assistant'
        self.content: str = content
        self.sources: list[DocumentSource] = sources or []
        self.timestamp: datetime = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "sources": [s.model_dump() for s in self.sources],
            "timestamp": self.timestamp,
        }


class ChatService:
    """Q&A chat — LLM-only, no RAG retrieval."""

    COLLECTION = "chat_sessions"

    def __init__(self, db: AsyncIOMotorDatabase, llm_router: LLMRouter) -> None:
        self._db = db
        self._llm = llm_router

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_message_stream(
        self,
        session_id: str | None,
        user_message: str,
        patient_context: PatientProfile | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream assistant tokens for a user message, yielding StreamEvents.

        Creates a new session if *session_id* is None.
        Calls LLMRouter directly (no RAG retrieval).
        Persists both turns after completion; on mid-stream error
        only the user turn is persisted.

        Requirements: 1.1, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6.
        """
        session_id = session_id or str(uuid.uuid4())

        # Load session history and cap at 20 messages
        history = await self._load_history(session_id)
        history = history[-20:]

        now = datetime.now(timezone.utc)
        user_turn = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": user_message,
            "sources": [],
            "timestamp": now,
        }

        # Build context list from session history for LLMRouter
        context: list[dict] = [
            {"role": msg.get("role", "user"), "content": msg.get("content", "")}
            for msg in history
        ]

        # Build the full prompt: system prompt + patient context + user message
        prompt_parts = [ASSISTANT_QA_SYSTEM_PROMPT]
        if patient_context:
            prompt_parts.append(
                f"\nPatient context: {patient_context.model_dump_json()}"
            )
        prompt_parts.append(f"\nUser: {user_message}")
        prompt = "\n".join(prompt_parts)

        assembled_answer = ""
        last_llm_used = ""
        last_fallback_used = False
        had_error = False

        try:
            async for chunk in self._llm.generate_stream(prompt, context):
                if chunk.error:
                    had_error = True
                    yield StreamEvent(
                        type="error",
                        error=chunk.error,
                        retryable=True,
                    )
                elif chunk.token:
                    cleaned = _strip_model_markers(chunk.token)
                    if cleaned:
                        assembled_answer += cleaned
                        last_llm_used = chunk.llm_used
                        last_fallback_used = chunk.fallback_used
                        yield StreamEvent(
                            type="token",
                            content=cleaned,
                        )
        except Exception as exc:
            had_error = True
            logger.exception("LLM stream failed: %s", exc)
            yield StreamEvent(
                type="error",
                error=str(exc),
                retryable=True,
            )

        # --- Persist turns to MongoDB ---
        if had_error:
            # Mid-stream error: persist user turn only
            try:
                async with timed_db_op(self.COLLECTION, "update_one"):
                    await self._db[self.COLLECTION].update_one(
                        {"session_id": session_id},
                        {
                            "$push": {"messages": user_turn},
                            "$setOnInsert": {
                                "session_id": session_id,
                                "user_id": user_id,
                                "patient_context": patient_context.model_dump() if patient_context else None,
                                "created_at": now,
                            },
                            "$set": {"updated_at": now},
                        },
                        upsert=True,
                    )
            except Exception:
                logger.exception("Failed to persist user turn after stream error")
        else:
            # Successful stream: emit done event and persist both turns
            assembled_answer = _strip_model_markers(assembled_answer).strip()
            yield StreamEvent(
                type="done",
                answer=assembled_answer,
                sources=[],
                llm_used=last_llm_used,
                fallback_used=last_fallback_used,
            )

            assistant_turn = {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": assembled_answer,
                "sources": [],
                "timestamp": now,
            }
            try:
                async with timed_db_op(self.COLLECTION, "update_one"):
                    await self._db[self.COLLECTION].update_one(
                        {"session_id": session_id},
                        {
                            "$push": {"messages": {"$each": [user_turn, assistant_turn]}},
                            "$setOnInsert": {
                                "session_id": session_id,
                                "user_id": user_id,
                                "patient_context": patient_context.model_dump() if patient_context else None,
                                "created_at": now,
                            },
                            "$set": {"updated_at": now},
                        },
                        upsert=True,
                    )
            except Exception:
                logger.exception("Failed to persist turns after stream completion")

    async def get_history(self, session_id: str, user_id: str | None = None) -> dict | None:
        """Return the full session document or None if not found.

        When *user_id* is provided the query also filters by owner so that
        only the session owner (or an admin who omits user_id) can retrieve it.
        """
        query: dict = {"session_id": session_id}
        if user_id is not None:
            query["user_id"] = user_id
        async with timed_db_op(self.COLLECTION, "find_one"):
            return await self._db[self.COLLECTION].find_one(query, {"_id": 0})

    async def list_sessions(self, user_id: str, skip: int = 0, limit: int = 20) -> list[dict]:
        """Return the user's chat sessions sorted by most recently updated.

        Each entry contains session_id, created_at, updated_at, and a preview
        of the first message (via ``$slice``).
        """
        async with timed_db_op(self.COLLECTION, "find"):
            cursor = (
                self._db[self.COLLECTION]
                .find(
                    {"user_id": user_id},
                    {
                        "session_id": 1,
                        "created_at": 1,
                        "updated_at": 1,
                        "messages": {"$slice": 1},
                        "_id": 0,
                    },
                )
                .sort("updated_at", -1)
                .skip(skip)
                .limit(limit)
            )
            return await cursor.to_list(length=limit)

    async def get_history_paginated(
        self,
        session_id: str,
        user_id: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict | None:
        """Return a paginated window of messages for a session.

        Uses MongoDB ``$slice`` for the message window and an aggregation
        pipeline to compute ``total_messages``.
        """
        query: dict = {"session_id": session_id}
        if user_id is not None:
            query["user_id"] = user_id

        async with timed_db_op(self.COLLECTION, "find_one"):
            doc = await self._db[self.COLLECTION].find_one(
                query,
                {
                    "session_id": 1,
                    "messages": {"$slice": [skip, limit]},
                    "patient_context": 1,
                    "created_at": 1,
                    "updated_at": 1,
                    "_id": 0,
                },
            )
        if doc is None:
            return None

        async with timed_db_op(self.COLLECTION, "aggregate"):
            total = await self._db[self.COLLECTION].aggregate([
                {"$match": {"session_id": session_id}},
                {"$project": {"total": {"$size": "$messages"}}},
            ]).to_list(1)
        doc["total_messages"] = total[0]["total"] if total else 0
        return doc

    async def delete_session(self, session_id: str, user_id: str | None = None) -> bool:
        """Delete a chat session. Returns True if a document was removed."""
        query: dict = {"session_id": session_id}
        if user_id is not None:
            query["user_id"] = user_id
        async with timed_db_op(self.COLLECTION, "delete_one"):
            result = await self._db[self.COLLECTION].delete_one(query)
        return result.deleted_count > 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_history(self, session_id: str) -> list[dict]:
        async with timed_db_op(self.COLLECTION, "find_one"):
            doc = await self._db[self.COLLECTION].find_one(
                {"session_id": session_id},
                {"messages": 1, "_id": 0},
            )
        return doc.get("messages", []) if doc else []
