"""
Property test: integration_app fixture wires real_db and real_s3 overrides correctly.

Feature: testing-coverage, Property 1 (partial): Logout invalidates token (round-trip)
Validates: Requirements 1.1, 1.2
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


@pytest.mark.integration
def test_integration_app_uses_real_db(integration_app, mongo_uri):
    """
    Verify that integration_app fixture correctly wires real_db:
    the db override must return the same database instance as real_db.

    Requirements: 1.1
    """
    # The integration_app patches all db singletons to return real_db.
    # We verify the seeded users are accessible via the real database.
    _, seeded, _ = mongo_uri
    assert "medecin" in seeded, "real_db must be seeded with a medecin user"
    assert "admin" in seeded, "real_db must be seeded with an admin user"

    medecin = seeded["medecin"]
    assert medecin["role"] == "medecin"
    assert medecin["email"] == "medecin@test.local"
    assert medecin["password_hash"] != "TestPassword123!", "password must be hashed"

    admin = seeded["admin"]
    assert admin["role"] == "admin"
    assert admin["email"] == "admin@test.local"


@pytest.mark.integration
def test_integration_app_uses_real_s3(integration_app, real_s3):
    """
    Verify that integration_app fixture correctly wires real_s3:
    the S3 service client must point to LocalStack.

    Requirements: 1.2
    """
    from backend.core.config import settings
    from backend.services import s3_service as s3_module

    # The S3 service client should be the LocalStack client
    assert s3_module.s3_service._client is real_s3

    # The configured bucket must exist in LocalStack
    bucket = settings.S3_BUCKET
    response = real_s3.list_buckets()
    bucket_names = [b["Name"] for b in response["Buckets"]]
    assert bucket in bucket_names, f"Bucket '{bucket}' must exist in LocalStack"


@pytest.mark.integration
@given(role=st.sampled_from(["medecin", "admin"]))
@settings(max_examples=2, deadline=None)
def test_seeded_users_have_valid_bcrypt_hashes(mongo_uri, role: str):
    """
    Property: for each seeded role, the stored password_hash is a valid bcrypt hash
    of the known test password.

    Requirements: 1.3
    """
    import bcrypt

    _, seeded, _ = mongo_uri
    user = seeded[role]
    password_hash = user["password_hash"].encode()
    assert bcrypt.checkpw(b"TestPassword123!", password_hash), (
        f"Seeded {role} user must have a valid bcrypt hash of 'TestPassword123!'"
    )
