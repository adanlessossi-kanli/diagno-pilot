"""
Property 11: Migration Script Idempotence (migrate_redesign)

**Validates: Requirements 10.2**

For any initial collection of chat_sessions documents (size 0–100),
running the migration 1–3 times SHALL always result in 0 documents
remaining in chat_sessions, no errors on subsequent runs, and indexes
created on document_chat_sessions and topic_guard_feedback.
"""
from __future__ import annotations

import copy
from typing import Any

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.scripts.migrate_redesign import migrate, create_indexes


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_non_empty_str = st.text(min_size=1, max_size=80).filter(lambda s: s.strip() != "")

_chat_session_st = st.fixed_dictionaries({
    "_id": _non_empty_str,
    "session_id": _non_empty_str,
    "user_id": _non_empty_str,
    "messages": st.just([]),
})


# ---------------------------------------------------------------------------
# In-memory MongoDB simulation for migration testing
# ---------------------------------------------------------------------------

class _DeleteResult:
    """Mimics pymongo DeleteResult."""

    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


class _InMemoryCollection:
    """Minimal in-memory collection supporting delete_many and create_index."""

    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self._docs: list[dict[str, Any]] = [copy.deepcopy(d) for d in (docs or [])]
        self._indexes: dict[str, Any] = {}

    async def delete_many(self, filter_: dict) -> _DeleteResult:
        if not filter_:
            # delete_many({}) removes all documents
            count = len(self._docs)
            self._docs.clear()
            return _DeleteResult(count)
        # Simple field-match filter for completeness
        remaining: list[dict[str, Any]] = []
        deleted = 0
        for doc in self._docs:
            if all(doc.get(k) == v for k, v in filter_.items()):
                deleted += 1
            else:
                remaining.append(doc)
        self._docs = remaining
        return _DeleteResult(deleted)

    async def create_index(self, keys, **kwargs) -> str:
        name = kwargs.get("name", str(keys))
        self._indexes[name] = keys
        return name

    def snapshot(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._docs)

    def count(self) -> int:
        return len(self._docs)


class _InMemoryDB:
    """Minimal in-memory DB that routes collection names."""

    def __init__(self, collections: dict[str, _InMemoryCollection] | None = None) -> None:
        self._collections: dict[str, _InMemoryCollection] = collections or {}

    def __getitem__(self, name: str) -> _InMemoryCollection:
        if name not in self._collections:
            self._collections[name] = _InMemoryCollection()
        return self._collections[name]


# ---------------------------------------------------------------------------
# Property 11 — Migration idempotence
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    docs=st.lists(_chat_session_st, min_size=0, max_size=100),
    run_count=st.integers(min_value=1, max_value=3),
)
@pytest.mark.asyncio
async def test_property_11_migration_idempotence(
    docs: list[dict[str, Any]],
    run_count: int,
) -> None:
    """Running migrate() 1–3 times always leaves 0 documents in chat_sessions.

    **Validates: Requirements 10.2**
    """
    chat_sessions = _InMemoryCollection(docs)
    db = _InMemoryDB({"chat_sessions": chat_sessions})

    for _ in range(run_count):
        await migrate(db)

    assert chat_sessions.count() == 0, (
        f"Expected 0 documents after {run_count} migration run(s), "
        f"got {chat_sessions.count()}"
    )


# ---------------------------------------------------------------------------
# Property 11 — create_indexes idempotence
# ---------------------------------------------------------------------------

@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(run_count=st.integers(min_value=1, max_value=3))
@pytest.mark.asyncio
async def test_property_11_create_indexes_idempotent(
    run_count: int,
) -> None:
    """Running create_indexes() multiple times does not raise errors and indexes exist.

    **Validates: Requirements 10.2**
    """
    db = _InMemoryDB()

    for _ in range(run_count):
        await create_indexes(db)

    doc_chat_col = db["document_chat_sessions"]
    feedback_col = db["topic_guard_feedback"]

    assert "session_id_1" in doc_chat_col._indexes
    assert "user_id_1_updated_at_-1" in doc_chat_col._indexes
    assert "user_id_1_timestamp_-1" in feedback_col._indexes


# ---------------------------------------------------------------------------
# Edge-case: empty collection migration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edge_empty_collection_migration() -> None:
    """Migrating an empty chat_sessions collection succeeds with 0 deletions.

    **Validates: Requirements 10.2**
    """
    chat_sessions = _InMemoryCollection([])
    db = _InMemoryDB({"chat_sessions": chat_sessions})

    await migrate(db)

    assert chat_sessions.count() == 0


# ---------------------------------------------------------------------------
# Edge-case: full migration + indexes combined
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edge_full_migration_and_indexes() -> None:
    """Running migrate() then create_indexes() leaves clean state with indexes.

    **Validates: Requirements 10.2**
    """
    docs = [{"_id": f"s{i}", "session_id": f"sid-{i}", "user_id": "u1"} for i in range(5)]
    chat_sessions = _InMemoryCollection(docs)
    db = _InMemoryDB({"chat_sessions": chat_sessions})

    await migrate(db)
    await create_indexes(db)

    assert chat_sessions.count() == 0
    assert "session_id_1" in db["document_chat_sessions"]._indexes
    assert "user_id_1_updated_at_-1" in db["document_chat_sessions"]._indexes
    assert "user_id_1_timestamp_-1" in db["topic_guard_feedback"]._indexes
