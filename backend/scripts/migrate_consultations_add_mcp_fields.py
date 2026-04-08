"""
Migration: add MCP fields to consultations and create supporting indexes.

Adds ``mcp_session_id`` (null), ``agent_contributions`` ([]) and
``evidence_citations`` ([]) to existing consultation documents that lack them.

Creates indexes:
  - consultations.mcp_session_id  (sparse)
  - consultations.{user_id: 1, created_at: -1}
  - diagnostic_audit.{user_id: 1, patient_id: 1, created_at: -1}

Idempotent — safe to run multiple times.

Run standalone:
    python -m backend.scripts.migrate_consultations_add_mcp_fields

Rollback:
    python -m backend.scripts.migrate_consultations_add_mcp_fields --rollback
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def migrate(db) -> None:
    """Add MCP fields to consultation documents that do not have them yet."""
    collection = db["consultations"]

    result = await collection.update_many(
        {"mcp_session_id": {"$exists": False}},
        {
            "$set": {
                "mcp_session_id": None,
                "agent_contributions": [],
                "evidence_citations": [],
            }
        },
    )
    logger.info(
        "Migration complete: %d document(s) updated with MCP fields.",
        result.modified_count,
    )


async def create_indexes(db) -> None:
    """Create indexes required by the MCP pipeline."""
    created = 0

    await db["consultations"].create_index(
        "mcp_session_id",
        sparse=True,
        name="mcp_session_id_1",
    )
    created += 1

    await db["consultations"].create_index(
        [("user_id", 1), ("created_at", -1)],
        name="user_id_1_created_at_-1",
    )
    created += 1

    await db["diagnostic_audit"].create_index(
        [("user_id", 1), ("patient_id", 1), ("created_at", -1)],
        name="user_id_1_patient_id_1_created_at_-1",
    )
    created += 1

    logger.info("%d index(es) created.", created)


async def rollback(db) -> None:
    """Remove MCP fields from migrated-but-unused documents and drop indexes."""
    result = await db["consultations"].update_many(
        {"mcp_session_id": None},
        {
            "$unset": {
                "mcp_session_id": "",
                "agent_contributions": "",
                "evidence_citations": "",
            }
        },
    )
    logger.info(
        "Rollback: %d document(s) reverted (mcp_session_id was null).",
        result.modified_count,
    )

    for col, idx_name in [
        ("consultations", "mcp_session_id_1"),
        ("consultations", "user_id_1_created_at_-1"),
        ("diagnostic_audit", "user_id_1_patient_id_1_created_at_-1"),
    ]:
        try:
            await db[col].drop_index(idx_name)
            logger.info("Dropped index %s on %s.", idx_name, col)
        except Exception:
            logger.warning("Index %s on %s not found — skipping.", idx_name, col)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate consultations collection for MCP fields."
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the migration (remove MCP fields and indexes).",
    )
    args = parser.parse_args()

    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/diagno_pilot")
    db_name = uri.rsplit("/", 1)[-1].split("?")[0] or "diagno_pilot"

    client: AsyncIOMotorClient = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[db_name]
        if args.rollback:
            await rollback(db)
        else:
            await migrate(db)
            await create_indexes(db)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
