"""
Unit tests for audit logging — locale, region, and protocol_version fields.

Validates: Requirements 10.1, 10.2, 11.3
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.audit_service import AuditService


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_capture():
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
    return AuditService(), captured, mock_db



# ---------------------------------------------------------------------------
# AuditService.log_action — locale and region in details
# ---------------------------------------------------------------------------

def test_locale_and_region_included_in_details():
    """When locale and region are passed, they appear in the persisted details."""
    service, captured, mock_db = _make_capture()
    with patch("backend.services.audit_service.db") as m:
        m.get_db.return_value = mock_db
        run(service.log_action(
            user_id="user1", action="create_prescription", resource="prescriptions",
            locale="fr-TG", region="TG",
        ))
    details = captured[0]["details"]
    assert details["locale"] == "fr-TG"
    assert details["region"] == "TG"


def test_locale_only_when_region_absent():
    service, captured, mock_db = _make_capture()
    with patch("backend.services.audit_service.db") as m:
        m.get_db.return_value = mock_db
        run(service.log_action(user_id="u", action="a", resource="r", locale="fr-BJ"))
    details = captured[0]["details"]
    assert details["locale"] == "fr-BJ"
    assert "region" not in details


def test_region_only_when_locale_absent():
    service, captured, mock_db = _make_capture()
    with patch("backend.services.audit_service.db") as m:
        m.get_db.return_value = mock_db
        run(service.log_action(user_id="u", action="a", resource="r", region="BJ"))
    details = captured[0]["details"]
    assert details["region"] == "BJ"
    assert "locale" not in details


def test_neither_locale_nor_region_leaves_details_unchanged():
    service, captured, mock_db = _make_capture()
    with patch("backend.services.audit_service.db") as m:
        m.get_db.return_value = mock_db
        run(service.log_action(
            user_id="u", action="a", resource="r",
            details={"existing_key": "value"},
        ))
    assert captured[0]["details"] == {"existing_key": "value"}


def test_locale_region_merged_with_existing_details():
    service, captured, mock_db = _make_capture()
    with patch("backend.services.audit_service.db") as m:
        m.get_db.return_value = mock_db
        run(service.log_action(
            user_id="u", action="a", resource="r",
            details={"antibiotic": "amoxicillin"},
            locale="en", region="ALL",
        ))
    details = captured[0]["details"]
    assert details["antibiotic"] == "amoxicillin"
    assert details["locale"] == "en"
    assert details["region"] == "ALL"


# ---------------------------------------------------------------------------
# PrescriptionService — audit record contains locale, region, protocol_version
# ---------------------------------------------------------------------------

def test_prescription_audit_record_contains_locale_region_protocol_version():
    """
    When calculate_prescription is called, the audit log record must contain
    locale, region, and protocol_version.

    Validates: Requirements 10.2, 11.3
    """
    from backend.models.patient import PatientProfile, Comorbidities
    from backend.models.common import AgeGroup
    from backend.services.prescription_service import PrescriptionService, AntibioticProtocol

    audit_calls: list[dict] = []

    async def fake_log_action(user_id, action, resource, details=None,
                              resource_id=None, ip_address=None,
                              locale=None, region=None):
        audit_calls.append({
            "user_id": user_id, "action": action, "resource": resource,
            "details": details or {}, "locale": locale, "region": region,
        })
        return "fake_id"

    protocol = AntibioticProtocol(
        name="amoxicillin", paediatric_dose_per_kg=50.0, adult_max_dose_mg=3000.0,
        frequency="3x/day", duration_days=7, route="oral",
        version="2025-01-15T00:00:00Z", available_regions=["TG", "BJ"],
    )
    patient = PatientProfile(
        age_group=AgeGroup.ADULT, weight_kg=70.0,
        comorbidities=Comorbidities(renal_failure=False, hepatic_failure=False),
    )

    svc = PrescriptionService()
    svc._protocols_cache = {("amoxicillin", "ALL"): protocol}

    with patch("backend.services.prescription_service.audit_service") as mock_audit:
        mock_audit.log_action = fake_log_action
        with patch("backend.services.prescription_service.PrescriptionService._get_drug_catalogue_entry",
                   new=AsyncMock(return_value=None)):
            rx = run(svc.calculate_prescription(
                antibiotic="amoxicillin", patient=patient,
                locale="fr-TG", region="TG",
            ))

    assert rx.locale == "fr-TG"
    assert rx.region == "TG"
    assert rx.protocol_version == "2025-01-15T00:00:00Z"

    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["locale"] == "fr-TG"
    assert call["region"] == "TG"
    assert call["details"]["protocol_version"] == "2025-01-15T00:00:00Z"
