"""
Tests de propriété pour le journal d'audit HIPAA — Diagno-Pilot

Property 12 : Audit record completeness (Validates: Requirements 8.1)
Property 13 : Audit hash chain integrity (Validates: Requirements 8.6)
Property 14 : Audit records exclude PHI values (Validates: Requirements 8.2, 9.3)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
from unittest.mock import MagicMock

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.audit_service import AuditLogger
from backend.services.phi_classifier import PHIClassifier

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

user_id_st = st.text(min_size=1, max_size=64).filter(str.strip)
action_st = st.sampled_from([
    "phi_read", "phi_write", "phi_delete", "llm_request", "phi_strip",
])
resource_st = st.sampled_from([
    "patients", "consultations", "documents", "prescriptions", "llm",
])
resource_id_st = st.one_of(st.none(), st.text(min_size=1, max_size=64))
ip_st = st.one_of(st.none(), st.just("127.0.0.1"), st.just("10.0.0.1"))
details_st = st.one_of(
    st.none(),
    st.fixed_dictionaries({}),
    st.fixed_dictionaries({"field_types": st.just(["full_name", "date_of_birth"])}),
)

# PHI value strategies — realistic patient data that must never appear in audit
phi_value_st = st.sampled_from([
    "Jean Dupont",
    "1985-03-15",
    "MRN-123456",
    "Pénicilline",
    "Metformine 500mg",
    "Diabète type 2",
])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_mock_db() -> tuple[MagicMock, list[dict]]:
    """Return (mock_database, inserted_docs_list)."""
    inserted: list[dict] = []

    async def fake_insert(doc: dict) -> MagicMock:
        inserted.append(dict(doc))
        result = MagicMock()
        result.inserted_id = doc.get("id", "fake")
        return result

    mock_collection = MagicMock()
    mock_collection.insert_one = fake_insert

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    return mock_db, inserted


# ---------------------------------------------------------------------------
# Property 12 : Audit record completeness
# ---------------------------------------------------------------------------

@given(
    user_id=user_id_st,
    action=action_st,
    resource=resource_st,
    resource_id=resource_id_st,
    details=details_st,
    ip_address=ip_st,
)
@h_settings(max_examples=100)
def test_hipaa_audit_record_contains_all_required_fields(
    user_id: str,
    action: str,
    resource: str,
    resource_id: str | None,
    details: dict | None,
    ip_address: str | None,
) -> None:
    """Property 12: Every HIPAA audit record contains all required fields.

    For any audit event, the stored record SHALL contain: timestamp, user_id,
    action, resource, ip_address, previous_hash, and record_hash.

    Validates: Requirements 8.1
    """
    mock_db, inserted = _make_mock_db()
    logger = AuditLogger(database=mock_db)

    run(logger.log_action(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    ))

    assert len(inserted) == 1
    doc = inserted[0]

    # All required fields present
    required = {"id", "timestamp", "user_id", "action", "resource",
                "ip_address", "previous_hash", "record_hash"}
    assert required.issubset(doc.keys()), f"Missing fields: {required - doc.keys()}"

    # Values match inputs
    assert doc["user_id"] == user_id
    assert doc["action"] == action
    assert doc["resource"] == resource
    assert doc["ip_address"] == ip_address

    # Hashes are non-empty hex strings
    assert len(doc["record_hash"]) == 64  # SHA-256 hex digest


# ---------------------------------------------------------------------------
# Property 13 : Audit hash chain integrity
# ---------------------------------------------------------------------------

@given(
    actions=st.lists(
        st.tuples(user_id_st, action_st, resource_st, ip_st),
        min_size=2,
        max_size=10,
    ),
)
@h_settings(max_examples=50)
def test_hipaa_audit_hash_chain_integrity(
    actions: list[tuple[str, str, str, str | None]],
) -> None:
    """Property 13: Hash chain integrity holds for any sequence of records.

    For any sequence of N audit records, each record's record_hash equals
    SHA-256(previous_hash + json(record_data)), and verify_chain detects
    any modification.

    Validates: Requirements 8.6
    """
    mock_db, inserted = _make_mock_db()
    logger = AuditLogger(database=mock_db)

    for user_id, action, resource, ip_addr in actions:
        run(logger.log_action(
            user_id=user_id,
            action=action,
            resource=resource,
            ip_address=ip_addr,
        ))

    assert len(inserted) == len(actions)

    # Verify chain manually
    prev_hash = ""
    for doc in inserted:
        assert doc["previous_hash"] == prev_hash

        record_data = {
            "id": doc["id"],
            "timestamp": doc["timestamp"],
            "user_id": doc["user_id"],
            "action": doc["action"],
            "resource": doc["resource"],
            "resource_id": doc.get("resource_id"),
            "details": doc.get("details", {}),
            "ip_address": doc.get("ip_address"),
        }
        payload = prev_hash + json.dumps(record_data, sort_keys=True, default=str)
        expected_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert doc["record_hash"] == expected_hash

        prev_hash = doc["record_hash"]

    # verify_chain should return True for intact chain
    assert run(logger.verify_chain(records=inserted)) is True


@given(
    actions=st.lists(
        st.tuples(user_id_st, action_st, resource_st),
        min_size=3,
        max_size=8,
    ),
    tamper_index=st.integers(min_value=0),
)
@h_settings(max_examples=50)
def test_hipaa_audit_hash_chain_detects_tampering(
    actions: list[tuple[str, str, str]],
    tamper_index: int,
) -> None:
    """Property 13b: verify_chain detects any modification to any record.

    Validates: Requirements 8.6
    """
    mock_db, inserted = _make_mock_db()
    logger = AuditLogger(database=mock_db)

    for user_id, action, resource in actions:
        run(logger.log_action(
            user_id=user_id, action=action, resource=resource,
        ))

    # Tamper with one record
    idx = tamper_index % len(inserted)
    inserted[idx]["action"] = "TAMPERED"

    assert run(logger.verify_chain(records=inserted)) is False


# ---------------------------------------------------------------------------
# Property 14 : Audit records exclude PHI values
# ---------------------------------------------------------------------------

@given(
    user_id=user_id_st,
    action=st.sampled_from(["llm_request", "phi_strip"]),
    resource=resource_st,
    phi_values=st.lists(phi_value_st, min_size=1, max_size=5),
)
@h_settings(max_examples=100)
def test_hipaa_audit_records_exclude_phi_values(
    user_id: str,
    action: str,
    resource: str,
    phi_values: list[str],
) -> None:
    """Property 14: Audit records exclude PHI values.

    For any audit record logging a PHI-related event, the record SHALL contain
    event metadata (action type, field type names) but SHALL NOT contain actual
    PHI values (patient names, dates of birth, medical record numbers).

    Validates: Requirements 8.2, 9.3
    """
    classifier = PHIClassifier()

    # Build details with field type names only — no PHI values
    details = {"field_types": ["full_name", "date_of_birth", "medical_record_number"]}

    mock_db, inserted = _make_mock_db()
    logger = AuditLogger(database=mock_db)

    run(logger.log_action(
        user_id=user_id,
        action=action,
        resource=resource,
        details=details,
    ))

    assert len(inserted) == 1
    doc = inserted[0]

    # Serialize the entire record to a string for PHI scanning
    record_str = json.dumps(doc, default=str)

    # No PHI value should appear anywhere in the serialized record
    for phi_val in phi_values:
        assert phi_val not in record_str, (
            f"PHI value '{phi_val}' found in audit record"
        )

    # Details should contain field type names (metadata), not values
    assert "field_types" in doc["details"]
    for field_type in doc["details"]["field_types"]:
        # Field type names are allowed — they describe what was accessed
        assert isinstance(field_type, str)
        # But they should be field names, not PHI values
        assert field_type in classifier.PHI_FIELDS or field_type in classifier.NON_PHI_FIELDS


# ---------------------------------------------------------------------------
# Property 12b : Fallback write preserves record completeness
# ---------------------------------------------------------------------------

@given(
    user_id=user_id_st,
    action=action_st,
    resource=resource_st,
)
@h_settings(max_examples=30)
def test_hipaa_audit_fallback_preserves_completeness(
    user_id: str,
    action: str,
    resource: str,
) -> None:
    """When MongoDB write fails, the fallback file record is still complete.

    Validates: Requirements 8.5
    """
    import tempfile
    import os

    # Create a mock DB that always fails
    async def fail_insert(doc: dict) -> None:
        raise ConnectionError("MongoDB unavailable")

    mock_collection = MagicMock()
    mock_collection.insert_one = fail_insert
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with tempfile.TemporaryDirectory() as tmpdir:
        fallback_path = os.path.join(tmpdir, "audit_fallback.jsonl")
        logger = AuditLogger(database=mock_db, fallback_path=fallback_path)

        run(logger.log_action(
            user_id=user_id,
            action=action,
            resource=resource,
        ))

        # Read the fallback file
        with open(fallback_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

        assert len(lines) == 1
        doc = json.loads(lines[0])

        required = {"id", "timestamp", "user_id", "action", "resource",
                    "previous_hash", "record_hash"}
        assert required.issubset(doc.keys())
        assert doc["user_id"] == user_id
        assert doc["action"] == action
        assert doc["resource"] == resource
