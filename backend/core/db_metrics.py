"""Shared async context manager for MongoDB operation instrumentation."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from backend.core.metrics import db_errors_total, db_query_duration_seconds


@asynccontextmanager
async def timed_db_op(collection: str, operation: str) -> AsyncGenerator[None, None]:
    """Record duration and errors for a MongoDB operation.

    Usage:
        async with timed_db_op("patients", "find_one"):
            result = await db.patients.find_one({"_id": id})
    """
    t0 = time.perf_counter()
    try:
        yield
    except Exception:
        db_errors_total.labels(collection=collection, operation=operation).inc()
        raise
    finally:
        db_query_duration_seconds.labels(
            collection=collection, operation=operation
        ).observe(time.perf_counter() - t0)
