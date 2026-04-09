"""ChatService — multi-turn RAG conversational assistant (REQ-04)."""
from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.core.db_metrics import timed_db_op
from backend.models.document import DocumentSource
from backend.models.patient import PatientProfile
from backend.services.llamaindex_pipeline import LlamaIndexPipeline, StreamEvent

logger = logging.getLogger(__name__)


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

    async def send_message_stream(
        self,
        session_id: str | None,
        user_message: str,
        patient_context: PatientProfile | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream assistant tokens for a user message, yielding StreamEvents.

        Creates a new session if *session_id* is None.
        Persists both turns after the ``done`` event; on mid-stream error
        only the user turn is persisted.

        Requirements: 5.1, 5.2, 5.3, 5.4.
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

        assembled_answer = ""
        done_event: StreamEvent | None = None
        had_error = False

        async for event in self._rag.query_stream(
            question=user_message,
            context=patient_context,
            top_k=5,
            session_history=history,
        ):
            if event.type == "token":
                assembled_answer += event.content or ""
                yield event
            elif event.type == "done":
                done_event = event
                yield event
            elif event.type == "error":
                had_error = True
                yield event

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
        elif done_event is not None:
            # Successful stream: persist both user and assistant turns
            assistant_turn = {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": assembled_answer,
                "sources": [s.model_dump() for s in (done_event.sources or [])],
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
