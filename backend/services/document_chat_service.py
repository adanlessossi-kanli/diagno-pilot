"""DocumentChatService — RAG-powered document chat via LlamaIndexPipeline.

Requirements: 5.3, 5.7, 7.1, 7.2, 7.4, 7.5, 7.6
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.core.db_metrics import timed_db_op
from backend.models.document import DocumentSource
from backend.services.llamaindex_pipeline import LlamaIndexPipeline, StreamEvent

logger = logging.getLogger(__name__)


class DocumentChatService:
    """Document Chat — RAG-powered via LlamaIndexPipeline."""

    COLLECTION = "document_chat_sessions"

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
        user_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream assistant tokens for a user message, yielding StreamEvents.

        Creates a new session if *session_id* is None.
        Calls LlamaIndexPipeline.query_stream() for RAG retrieval.
        Persists both turns after completion; on mid-stream error
        only the user turn is persisted.

        Requirements: 7.1, 7.2, 7.4, 7.5.
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

        # Build session history for RAG pipeline
        session_history: list[dict] = [
            {"role": msg.get("role", "user"), "content": msg.get("content", "")}
            for msg in history
        ]

        assembled_answer = ""
        last_sources: list[DocumentSource] = []
        last_llm_used = ""
        last_fallback_used = False
        last_confidence_score: float | None = None
        had_error = False

        try:
            async for event in self._rag.query_stream(
                question=user_message,
                context=None,
                session_history=session_history,
            ):
                if event.type == "error":
                    had_error = True
                    yield event
                elif event.type == "token":
                    assembled_answer += event.content or ""
                    yield event
                elif event.type == "done":
                    assembled_answer = event.answer or assembled_answer
                    last_sources = event.sources or []
                    last_llm_used = event.llm_used or ""
                    last_fallback_used = event.fallback_used
                    last_confidence_score = event.confidence_score
                    # Don't yield done yet — we persist first, then yield
        except Exception as exc:
            had_error = True
            logger.exception("RAG stream failed: %s", exc)
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
                                "created_at": now,
                            },
                            "$set": {"updated_at": now},
                        },
                        upsert=True,
                    )
            except Exception:
                logger.exception("Failed to persist user turn after stream error")
        else:
            # Successful stream: persist both turns, then emit done event
            assistant_turn = {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": assembled_answer,
                "sources": [s.model_dump() for s in last_sources],
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
                                "created_at": now,
                            },
                            "$set": {"updated_at": now},
                        },
                        upsert=True,
                    )
            except Exception:
                logger.exception("Failed to persist turns after stream completion")

            yield StreamEvent(
                type="done",
                answer=assembled_answer,
                sources=last_sources,
                llm_used=last_llm_used,
                fallback_used=last_fallback_used,
                confidence_score=last_confidence_score,
            )

    async def get_history(self, session_id: str, user_id: str | None = None) -> dict | None:
        """Return the full session document or None if not found."""
        query: dict = {"session_id": session_id}
        if user_id is not None:
            query["user_id"] = user_id
        async with timed_db_op(self.COLLECTION, "find_one"):
            return await self._db[self.COLLECTION].find_one(query, {"_id": 0})

    async def get_history_paginated(
        self,
        session_id: str,
        user_id: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict | None:
        """Return a paginated window of messages for a session."""
        query: dict = {"session_id": session_id}
        if user_id is not None:
            query["user_id"] = user_id

        async with timed_db_op(self.COLLECTION, "find_one"):
            doc = await self._db[self.COLLECTION].find_one(
                query,
                {
                    "session_id": 1,
                    "messages": {"$slice": [skip, limit]},
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

    async def list_sessions(self, user_id: str, skip: int = 0, limit: int = 20) -> list[dict]:
        """Return the user's document chat sessions sorted by most recently updated."""
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

    async def delete_session(self, session_id: str, user_id: str | None = None) -> bool:
        """Delete a document chat session. Returns True if a document was removed."""
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
