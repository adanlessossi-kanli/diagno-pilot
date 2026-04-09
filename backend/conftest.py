import asyncio as _asyncio
import sys
import os

# Add the parent directory (project root) to sys.path so that
# "from backend.models import ..." works when running pytest from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    """Reset sse-starlette's AppStatus event so it binds to the current event loop.

    ``sse-starlette`` stores a module-level ``asyncio.Event`` that gets bound
    to the first event loop it encounters.  In pytest with
    ``asyncio_mode=strict`` each test gets a fresh loop, so the stale event
    raises ``RuntimeError: ... is bound to a different event loop``.
    Re-creating the event before every test avoids this.
    """
    try:
        from sse_starlette.sse import AppStatus
        AppStatus.should_exit_event = _asyncio.Event()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the in-memory rate limiter storage between tests to avoid cross-test interference."""
    from backend.core.rate_limit import limiter
    try:
        storage = limiter._storage
        if hasattr(storage, "_storage"):
            storage._storage.clear()
        elif hasattr(storage, "storage"):
            storage.storage.clear()
    except Exception:
        pass
    yield
    try:
        storage = limiter._storage
        if hasattr(storage, "_storage"):
            storage._storage.clear()
        elif hasattr(storage, "storage"):
            storage.storage.clear()
    except Exception:
        pass
