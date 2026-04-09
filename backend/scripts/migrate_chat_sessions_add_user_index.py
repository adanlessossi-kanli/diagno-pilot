"""
Migration: ensure compound index (user_id, updated_at) on chat_sessions.

This index supports the list_sessions query which filters by user_id and
sorts by updated_at descending.

Idempotent — safe to run multiple times.

Run standalone:
    python -m backend.scripts.migrate_chat_sessions_add_user_index
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


async def create_chat_sessions_user_index(db) -> None:
    """Create compound index on chat_sessions.(user_id, updated_at) (idempotent)."""
    collection = db["chat_sessions"]
    await collection.create_index(
        [("user_id", 1), ("updated_at", -1)],
        name="user_id_1_updated_at_-1",
        background=True,
    )
    logger.info("Compound index (user_id, updated_at) on chat_sessions ensured.")


async def main() -> None:
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/diagno_pilot")
    db_name = uri.rsplit("/", 1)[-1].split("?")[0] or "diagno_pilot"

    client: AsyncIOMotorClient = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        database = client[db_name]
        await create_chat_sessions_user_index(database)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
