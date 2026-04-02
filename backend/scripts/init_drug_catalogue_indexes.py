"""
Create MongoDB indexes for the drug_catalogue collection.

Run standalone:
    python -m backend.scripts.init_drug_catalogue_indexes
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


async def create_drug_catalogue_indexes(db) -> None:
    """Create indexes on the drug_catalogue collection."""
    collection = db["drug_catalogue"]

    # Unique index on inn
    await collection.create_index([("inn", 1)], unique=True, name="inn_unique")
    logger.info("Created unique index on drug_catalogue.inn")

    # Index on available_regions
    await collection.create_index([("available_regions", 1)], name="available_regions_idx")
    logger.info("Created index on drug_catalogue.available_regions")


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

    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[db_name]
        await create_drug_catalogue_indexes(db)
        await create_antibiotic_protocols_indexes(db)
        logger.info("All indexes created successfully.")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
