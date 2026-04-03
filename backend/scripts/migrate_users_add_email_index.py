"""
Migration: ensure unique index on users.email and add is_active/created_at fields
to any legacy user documents that are missing them.

Idempotent — safe to run multiple times.

Run standalone:
    python -m backend.scripts.migrate_users_add_email_index
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def migrate(db) -> None:
    """Backfill missing is_active and created_at fields on legacy user documents."""
    collection = db["users"]
    now = datetime.now(timezone.utc)

    result = await collection.update_many(
        {"is_active": {"$exists": False}},
        {"$set": {"is_active": True}},
    )
    logger.info("Backfilled is_active on %d user(s).", result.modified_count)

    result = await collection.update_many(
        {"created_at": {"$exists": False}},
        {"$set": {"created_at": now}},
    )
    logger.info("Backfilled created_at on %d user(s).", result.modified_count)


async def create_users_indexes(db) -> None:
    """Create unique index on users.email (idempotent)."""
    collection = db["users"]
    await collection.create_index("email", unique=True, name="email_unique_idx")
    logger.info("Unique index on users.email ensured.")


async def main() -> None:
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/diagno_pilot")
    db_name = uri.rsplit("/", 1)[-1].split("?")[0] or "diagno_pilot"

    client: AsyncIOMotorClient = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        database = client[db_name]
        await migrate(database)
        await create_users_indexes(database)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
