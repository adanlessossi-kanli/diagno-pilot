"""
Migration: add region and available_regions fields to antibiotic_protocols documents.

Also creates the compound index { name: 1, region: 1, created_at: -1 } on the
antibiotic_protocols collection.

Idempotent — safe to run multiple times.

Run standalone:
    python -m backend.scripts.migrate_protocols_add_region
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
    """Assign region='ALL' and available_regions=['TG','BJ'] to legacy documents."""
    collection = db["antibiotic_protocols"]

    # Only update documents that do NOT already have a region field
    result = await collection.update_many(
        {"region": {"$exists": False}},
        {"$set": {"region": "ALL", "available_regions": ["TG", "BJ"]}},
    )
    logger.info(
        "Migration complete: %d document(s) updated with region='ALL'.",
        result.modified_count,
    )


async def create_antibiotic_protocols_indexes(db) -> None:
    """Create compound index on antibiotic_protocols for region-aware lookup."""
    collection = db["antibiotic_protocols"]

    await collection.create_index(
        [("name", 1), ("region", 1), ("created_at", -1)],
        name="name_region_created_at_idx",
    )
    logger.info(
        "Created compound index { name: 1, region: 1, created_at: -1 } "
        "on antibiotic_protocols."
    )


async def main() -> None:
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/diagno_pilot")
    db_name = uri.rsplit("/", 1)[-1].split("?")[0] or "diagno_pilot"

    client: AsyncIOMotorClient = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[db_name]
        await migrate(db)
        await create_antibiotic_protocols_indexes(db)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
