import sys
import os

# Add the parent directory (project root) to sys.path so that
# "from backend.models import ..." works when running pytest from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


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
