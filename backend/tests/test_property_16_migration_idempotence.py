"""
Property 16: Idempotence de la migration et préservation des champs

**Validates: Requirements 12.5, 12.6**

Pour tout état de la base de données, exécuter le script de migration deux fois
doit produire le même état que l'exécuter une seule fois (f(f(x)) = f(x)).
De plus, pour tout document Consultation existant, tous les champs originaux
doivent être préservés inchangés après la migration.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.scripts.migrate_consultations_add_mcp_fields import (
    migrate,
    create_indexes,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_non_empty_str = st.text(min_size=1, max_size=80).filter(lambda s: s.strip() != "")

_symptom_st = st.fixed_dictionaries({
    "name": _non_empty_str,
    "severity": st.one_of(st.none(), st.sampled_from(["mild", "moderate", "severe"])),
    "duration_days": st.one_of(st.none(), st.integers(min_value=0, max_value=365)),
})

_diagnosis_st = st.fixed_dictionaries({
    "condition": _non_empty_str,
    "probability": st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    "icd_code": st.one_of(st.none(), st.text(min_size=3, max_size=8)),
    "matching_symptoms": st.lists(st.text(min_size=1, max_size=20), max_size=5),
})

_created_at_st = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)

_legacy_consultation_st = st.fixed_dictionaries({
    "_id": _non_empty_str,
    "user_id": _non_empty_str,
    "patient_id": st.one_of(st.none(), _non_empty_str),
    "symptoms": st.lists(_symptom_st, min_size=1, max_size=5),
    "diagnoses": st.lists(_diagnosis_st, min_size=0, max_size=5),
    "llm_used": st.one_of(st.none(), _non_empty_str),
    "is_one_shot": st.booleans(),
    "created_at": _created_at_st,
    "alerts": st.just([]),
})


# ---------------------------------------------------------------------------
# In-memory MongoDB simulation for migration testing
# ---------------------------------------------------------------------------

class _InMemoryCollection:
    """Minimal in-memory collection that supports update_many and create_index."""

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = [copy.deepcopy(d) for d in docs]
        self._indexes: dict[str, Any] = {}

    async def update_many(self, filter_: dict, update: dict):
        matched = 0
        modified = 0
        for doc in self._docs:
            if self._matches(doc, filter_):
                matched += 1
                if "$set" in update:
                    for k, v in update["$set"].items():
                        if doc.get(k) != v:
                            modified += 1
                        doc[k] = v
        result = MagicMock()
        result.matched_count = matched
        result.modified_count = modified
        return result

    async def create_index(self, keys, **kwargs):
        name = kwargs.get("name", str(keys))
        self._indexes[name] = keys

    def snapshot(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._docs)

    @staticmethod
    def _matches(doc: dict, filter_: dict) -> bool:
        for key, condition in filter_.items():
            if isinstance(condition, dict):
                for op, val in condition.items():
                    if op == "$exists" and val is False:
                        if key in doc:
                            return False
                    elif op == "$exists" and val is True:
                        if key not in doc:
                            return False
            else:
                if doc.get(key) != condition:
                    return False
        return True


class _InMemoryDB:
    """Minimal in-memory DB that routes collection names."""

    def __init__(self, collections: dict[str, _InMemoryCollection]) -> None:
        self._collections = collections

    def __getitem__(self, name: str) -> _InMemoryCollection:
        if name not in self._collections:
            self._collections[name] = _InMemoryCollection([])
        return self._collections[name]


# ---------------------------------------------------------------------------
# Property 16 — Idempotence of migration and field preservation
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(docs=st.lists(_legacy_consultation_st, min_size=0, max_size=10))
@pytest.mark.asyncio
async def test_property_16_migration_idempotence(
    docs: list[dict[str, Any]],
) -> None:
    """Running migrate() twice produces the same state as running it once.

    **Validates: Requirements 12.5, 12.6**
    """
    # --- First run ---
    col1 = _InMemoryCollection(docs)
    db1 = _InMemoryDB({"consultations": col1, "diagnostic_audit": _InMemoryCollection([])})
    await migrate(db1)
    state_after_first = col1.snapshot()

    # --- Second run (same state) ---
    col2 = _InMemoryCollection(state_after_first)
    db2 = _InMemoryDB({"consultations": col2, "diagnostic_audit": _InMemoryCollection([])})
    await migrate(db2)
    state_after_second = col2.snapshot()

    # f(f(x)) == f(x)
    assert state_after_first == state_after_second


@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(docs=st.lists(_legacy_consultation_st, min_size=1, max_size=10))
@pytest.mark.asyncio
async def test_property_16_migration_preserves_original_fields(
    docs: list[dict[str, Any]],
) -> None:
    """All original fields of existing documents are preserved after migration.

    **Validates: Requirements 12.5, 12.6**
    """
    originals = copy.deepcopy(docs)

    col = _InMemoryCollection(docs)
    db = _InMemoryDB({"consultations": col, "diagnostic_audit": _InMemoryCollection([])})
    await migrate(db)
    migrated = col.snapshot()

    for orig, mig in zip(originals, migrated):
        # Every original key must still be present with the same value
        for key, value in orig.items():
            assert key in mig, f"Field '{key}' was removed by migration"
            assert mig[key] == value, f"Field '{key}' was modified by migration"

        # New MCP fields must be present with defaults
        assert mig["mcp_session_id"] is None
        assert mig["agent_contributions"] == []
        assert mig["evidence_citations"] == []


# ---------------------------------------------------------------------------
# Edge-case: documents that already have MCP fields are untouched
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edge_already_migrated_documents_untouched() -> None:
    """Documents that already have mcp_session_id are not modified.

    **Validates: Requirements 12.5, 12.6**
    """
    doc_with_mcp = {
        "_id": "existing-mcp",
        "user_id": "doc-1",
        "symptoms": [{"name": "fever"}],
        "diagnoses": [],
        "created_at": datetime.now(timezone.utc),
        "mcp_session_id": "session-abc",
        "agent_contributions": [{"agent_name": "epi", "confidence_score": 0.9}],
        "evidence_citations": [{"document_id": "d1", "title": "T", "source": "S", "excerpt": "E"}],
    }
    original = copy.deepcopy(doc_with_mcp)

    col = _InMemoryCollection([doc_with_mcp])
    db = _InMemoryDB({"consultations": col, "diagnostic_audit": _InMemoryCollection([])})
    await migrate(db)
    result = col.snapshot()

    assert result[0] == original


@pytest.mark.asyncio
async def test_edge_create_indexes_idempotent() -> None:
    """Running create_indexes twice does not raise errors.

    **Validates: Requirement 12.5**
    """
    col = _InMemoryCollection([])
    audit_col = _InMemoryCollection([])
    db = _InMemoryDB({"consultations": col, "diagnostic_audit": audit_col})

    await create_indexes(db)
    await create_indexes(db)

    assert "mcp_session_id_1" in col._indexes
    assert "user_id_1_created_at_-1" in col._indexes
    assert "user_id_1_patient_id_1_created_at_-1" in audit_col._indexes
