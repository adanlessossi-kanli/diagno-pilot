#!/usr/bin/env python3
"""
CLI script for re-indexing existing document chunks via the LlamaIndex pipeline.

Usage:
    # Migrate all documents
    python -m scripts.migrate_chunks

    # Migrate a single document
    python -m scripts.migrate_chunks --document-id 6650a1b2c3d4e5f6a7b8c9d0

Requirements: 14.1–14.7
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from backend.core.database import db  # noqa: E402
from backend.services.migration_service import ChunkMigrationService  # noqa: E402
from backend.services.s3_service import s3_service  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main(document_id: str | None = None) -> int:
    """Run the migration and return exit code (0=success, 1=failures)."""
    await db.connect()
    try:
        database = db.get_db()
        service = ChunkMigrationService(db=database, s3=s3_service)

        if document_id:
            result = await service.migrate_document(document_id)
            if result.success:
                logger.info(
                    "Document %s migrated: %d → %d chunks",
                    document_id, result.old_chunk_count, result.new_chunk_count,
                )
                return 0
            else:
                logger.error("Migration failed: %s", result.error)
                return 1
        else:
            report = await service.migrate_all()
            logger.info(
                "Migration complete: %d/%d succeeded, %d failed.",
                report.succeeded, report.total, report.failed,
            )
            return 0 if report.failed == 0 else 1
    finally:
        await db.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-index document chunks via LlamaIndex pipeline")
    parser.add_argument("--document-id", type=str, default=None, help="Migrate a single document by ID")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.document_id)))
