"""
Migration: assistant-qa-and-documents-redesign.

1. Delete all existing chat session documents from ``chat_sessions``.
2. Create indexes on ``document_chat_sessions``:
   - ``session_id`` (unique)
   - ``(user_id, updated_at)`` compound
3. Create index on ``topic_guard_feedback``:
   - ``(user_id, timestamp)`` compound

Idempotent — safe to run multiple times.

Run standalone:
    python -m backend.scripts.migrate_redesign
"""
from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def migrate(db) -> None:
    """Delete all existing chat sessions (clean slate for redesign)."""
    collection = db["chat_sessions"]
    result = await collection.delete_many({})
    logger.info("Deleted %d chat session(s).", result.deleted_count)


async def create_indexes(db) -> None:
    """Create indexes for document_chat_sessions and topic_guard_feedback."""
    created = 0

    await db["document_chat_sessions"].create_index(
        "session_id",
        unique=True,
        name="session_id_1",
    )
    created += 1

    await db["document_chat_sessions"].create_index(
        [("user_id", 1), ("updated_at", -1)],
        name="user_id_1_updated_at_-1",
    )
    created += 1

    await db["topic_guard_feedback"].create_index(
        [("user_id", 1), ("timestamp", -1)],
        name="user_id_1_timestamp_-1",
    )
    created += 1

    logger.info("%d index(es) created.", created)


async def main() -> None:
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/diagno_pilot")
    db_name = uri.rsplit("/", 1)[-1].split("?")[0] or "diagno_pilot"

    client: AsyncIOMotorClient = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[db_name]
        await migrate(db)
        await create_indexes(db)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
