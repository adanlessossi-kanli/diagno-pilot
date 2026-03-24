"""
Tests de propriété pour le service d'audit — Diagno-Pilot

**Validates: Requirements REQ-10**

Propriété 2 : Toute action sensible génère exactement un log d'audit avec
utilisateur, action, ressource et horodatage.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.audit_service import AuditService

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

user_id_strategy = st.text(min_size=1, max_size=64).filter(str.strip)
action_strategy = st.sampled_from([
    "login", "logout", "create_patient", "update_patient",
    "create_consultation", "upload_document", "delete_document",
    "create_prescription",
])
resource_strategy = st.sampled_from([
    "auth", "patients", "consultations", "documents", "prescriptions", "files",
])
resource_id_strategy = st.one_of(st.none(), st.text(min_size=1, max_size=64))
ip_strategy = st.one_of(
    st.none(),
    st.just("127.0.0.1"),
    st.just("192.168.1.1"),
    st.just("10.0.0.1"),
)
details_strategy = st.one_of(
    st.none(),
    st.fixed_dictionaries({}),
    st.fixed_dictionaries({"key": st.text(max_size=32)}),
)


# ---------------------------------------------------------------------------
# Helper — run async in sync test
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Property 2a : log_action inserts exactly one document per call
# ---------------------------------------------------------------------------

@given(
    user_id=user_id_strategy,
    action=action_strategy,
    resource=resource_strategy,
    resource_id=resource_id_strategy,
    details=details_strategy,
    ip_address=ip_strategy,
)
@h_settings(max_examples=100)
def test_log_action_inserts_exactly_one_document(
    user_id: str,
    action: str,
    resource: str,
    resource_id: str | None,
    details: dict | None,
    ip_address: str | None,
):
    """
    **Validates: Requirements REQ-10**

    For any combination of valid inputs, `log_action` must insert exactly one
    document into the `audit_logs` collection.
    """
    inserted_docs: list[dict] = []

    async def fake_insert_one(doc):
        inserted_docs.append(doc)
        result = MagicMock()
        result.inserted_id = "fake_id"
        return result

    mock_collection = MagicMock()
    mock_collection.insert_one = fake_insert_one

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    service = AuditService()

    with patch("backend.services.audit_service.db") as mock_db_module:
        mock_db_module.get_db.return_value = mock_db
        run(service.log_action(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        ))

    assert len(inserted_docs) == 1, "Exactly one document must be inserted per log_action call"


# ---------------------------------------------------------------------------
# Property 2b : log document always contains required fields with correct values
# ---------------------------------------------------------------------------

@given(
    user_id=user_id_strategy,
    action=action_strategy,
    resource=resource_strategy,
    resource_id=resource_id_strategy,
    ip_address=ip_strategy,
)
@h_settings(max_examples=100)
def test_log_document_contains_required_fields(
    user_id: str,
    action: str,
    resource: str,
    resource_id: str | None,
    ip_address: str | None,
):
    """
    **Validates: Requirements REQ-10**

    The persisted audit document must always contain: user_id, action,
    resource, and created_at — with values matching the inputs.
    """
    captured: list[dict] = []

    async def fake_insert_one(doc):
        captured.append(dict(doc))
        result = MagicMock()
        result.inserted_id = "fake_id"
        return result

    mock_collection = MagicMock()
    mock_collection.insert_one = fake_insert_one

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    service = AuditService()

    before = datetime.now(timezone.utc)

    with patch("backend.services.audit_service.db") as mock_db_module:
        mock_db_module.get_db.return_value = mock_db
        run(service.log_action(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            ip_address=ip_address,
        ))

    after = datetime.now(timezone.utc)

    assert len(captured) == 1
    doc = captured[0]

    # Required fields present
    assert "user_id" in doc
    assert "action" in doc
    assert "resource" in doc
    assert "created_at" in doc

    # Values match inputs
    assert doc["user_id"] == user_id
    assert doc["action"] == action
    assert doc["resource"] == resource

    # Timestamp is within the test window
    ts: datetime = doc["created_at"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    assert before <= ts <= after, "created_at must be set at call time"


# ---------------------------------------------------------------------------
# Property 2c : details defaults to empty dict when None is passed
# ---------------------------------------------------------------------------

@given(
    user_id=user_id_strategy,
    action=action_strategy,
    resource=resource_strategy,
)
@h_settings(max_examples=50)
def test_log_details_defaults_to_empty_dict(user_id: str, action: str, resource: str):
    """
    **Validates: Requirements REQ-10**

    When `details` is not provided (None), the persisted document must contain
    an empty dict for the `details` field.
    """
    captured: list[dict] = []

    async def fake_insert_one(doc):
        captured.append(dict(doc))
        result = MagicMock()
        result.inserted_id = "fake_id"
        return result

    mock_collection = MagicMock()
    mock_collection.insert_one = fake_insert_one

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    service = AuditService()

    with patch("backend.services.audit_service.db") as mock_db_module:
        mock_db_module.get_db.return_value = mock_db
        run(service.log_action(user_id=user_id, action=action, resource=resource))

    assert captured[0]["details"] == {}
