"""ChatService — multi-turn RAG conversational assistant (REQ-04)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.core.db_metrics import timed_db_op
from backend.models.document import DocumentSource, RAGResponse
from backend.models.patient import PatientProfile
from backend.services.llamaindex_pipeline import LlamaIndexPipeline


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
    """Manages multi-turn chat sessions backed by MongoDB and RAGService."""

    COLLECTION = "chat_sessions"

    def __init__(self, db: AsyncIOMotorDatabase, rag_service: LlamaIndexPipeline) -> None:
        self._db = db
        self._rag = rag_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_message(
        self,
        session_id: str | None,
        user_message: str,
        patient_context: PatientProfile | None = None,
        user_id: str | None = None,
    ) -> tuple[str, RAGResponse]:
        """Process a user message and return (session_id, RAGResponse).

        Creates a new session if *session_id* is None.
        Persists both the user turn and the assistant turn in MongoDB.
        """
        session_id = session_id or str(uuid.uuid4())

        # Query RAG with the full conversation context
        rag_response = await self._rag.query(
            question=user_message,
            context=patient_context,
            top_k=5,
        )

        now = datetime.now(timezone.utc)
        user_turn = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": user_message,
            "sources": [],
            "timestamp": now,
        }
        assistant_turn = {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": rag_response.answer,
            "sources": [s.model_dump() for s in rag_response.sources],
            "timestamp": now,
        }

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

        return session_id, rag_response

    async def get_history(self, session_id: str) -> dict | None:
        """Return the full session document or None if not found."""
        async with timed_db_op(self.COLLECTION, "find_one"):
            return await self._db[self.COLLECTION].find_one(
                {"session_id": session_id},
                {"_id": 0},
            )

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
