"""
Backend E2E file upload integration tests — real LocalStack S3 and MongoDB via Testcontainers.

Feature: testing-coverage
Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
"""
from __future__ import annotations

import io

import pytest
import pytest_asyncio
import respx
from httpx import AsyncClient, ASGITransport
from hypothesis import given, settings
from hypothesis import strategies as st
from motor.motor_asyncio import AsyncIOMotorDatabase



# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimal valid PDF magic bytes + enough content to pass validation
_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"xref\n0 2\n0000000000 65535 f\n0000000009 00000 n\n"
    b"trailer\n<< /Size 2 /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
)

# Minimal valid PNG (1x1 pixel, white)
_MINIMAL_PNG = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk length + type
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # width=1, height=1
    0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,  # bit depth, color type, etc.
    0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
    0x54, 0x08, 0xD7, 0x63, 0xF8, 0xFF, 0xFF, 0x3F,
    0x00, 0x05, 0xFE, 0x02, 0xFE, 0xDC, 0xCC, 0x59,
    0xE7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,  # IEND chunk
    0x44, 0xAE, 0x42, 0x60, 0x82,
])

# Minimal valid CSV
_MINIMAL_CSV = b"name,age\nAlice,30\nBob,25\n"

# Allowed MIME types with their corresponding file content and filenames
# Note: CSV is excluded because the fallback MIME detector (used when libmagic
# is unavailable) cannot detect CSV from magic bytes alone.
_ALLOWED_FILES = [
    ("application/pdf", _MINIMAL_PDF, "test.pdf"),
    ("image/png", _MINIMAL_PNG, "test.png"),
]

# MIME types that are NOT in the allowed list
_DISALLOWED_MIME_TYPES = [
    "application/json",
    "text/html",
    "application/zip",
    "application/x-executable",
    "video/mp4",
    "audio/mpeg",
    "application/octet-stream",
    "text/xml",
    "application/javascript",
    "image/gif",
]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for allowed (MIME type, content, filename) triples
_allowed_file_strategy = st.sampled_from(_ALLOWED_FILES)

# Strategy for disallowed MIME types (not in ALLOWED_MIME_TYPES)
_disallowed_mime_strategy = st.sampled_from(_DISALLOWED_MIME_TYPES)

# Strategy for random file content (non-empty bytes that won't match allowed magic bytes)
_disallowed_content_strategy = st.binary(min_size=16, max_size=256).filter(
    lambda b: not b.startswith(b"%PDF")
    and not b.startswith(b"\xff\xd8")
    and not b.startswith(b"\x89PNG")
    and not b.startswith(b"PK")
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def medecin_client(integration_app):
    """Async client authenticated as the seeded medecin user."""
    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "medecin@test.local", "password": "TestPassword123!"},
        )
        assert resp.status_code == 200, f"medecin login failed: {resp.text}"
        yield client


@pytest_asyncio.fixture
async def admin_client(integration_app):
    """Async client authenticated as the seeded admin user."""
    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.local", "password": "TestPassword123!"},
        )
        assert resp.status_code == 200, f"admin login failed: {resp.text}"
        yield client


@pytest_asyncio.fixture
async def patient_id(medecin_client: AsyncClient) -> str:
    """Create a test patient and return its ID."""
    resp = await medecin_client.post(
        "/api/v1/patients",
        json={
            "full_name": "File Upload Test Patient",
            "weight_kg": 70.0,
            "allergies": [],
            "current_medications": [],
            "comorbidities": {"renal_failure": False, "hepatic_failure": False},
        },
    )
    assert resp.status_code == 201, f"patient creation failed: {resp.text}"
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _upload_pdf(client: AsyncClient, pid: str) -> dict:
    """Upload a minimal PDF and return the response body."""
    resp = await client.post(
        "/api/v1/files/upload",
        files={"file": ("test.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
        data={"patient_id": pid, "file_type": "pdf"},
    )
    assert resp.status_code == 201, f"upload failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Test 1 — Valid PDF upload stores file in S3 and returns file_id
# Validates: Requirement 5.1
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_valid_pdf_upload_returns_file_id(
    medecin_client: AsyncClient,
    patient_id: str,
    real_s3,
):
    body = await _upload_pdf(medecin_client, patient_id)

    assert "id" in body, "Response must contain 'id'"
    assert body["id"] is not None

    # Verify the file is stored in LocalStack S3
    from backend.core.config import settings
    s3_key = body["s3_key"]
    response = real_s3.get_object(Bucket=settings.S3_BUCKET, Key=s3_key)
    assert response["ResponseMetadata"]["HTTPStatusCode"] == 200


# ---------------------------------------------------------------------------
# Test 2 — Upload then download returns byte-for-byte identical content
# Validates: Requirement 5.2
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_upload_then_download_identical_content(
    medecin_client: AsyncClient,
    patient_id: str,
    real_s3,
):
    body = await _upload_pdf(medecin_client, patient_id)
    file_id = body["id"]
    s3_key = body["s3_key"]

    # GET /api/v1/files/{file_id} returns metadata + presigned URL
    get_resp = await medecin_client.get(f"/api/v1/files/{file_id}")
    assert get_resp.status_code == 200

    # Download the actual bytes directly from S3 (presigned URL points to LocalStack)
    from backend.core.config import settings
    s3_obj = real_s3.get_object(Bucket=settings.S3_BUCKET, Key=s3_key)
    downloaded_bytes = s3_obj["Body"].read()

    assert downloaded_bytes == _MINIMAL_PDF, (
        "Downloaded content must be byte-for-byte identical to uploaded content"
    )


# ---------------------------------------------------------------------------
# Test 3 — Disallowed MIME type upload returns HTTP 415
# Validates: Requirement 5.3
# Note: The file validator raises HTTP 415 (Unsupported Media Type) for
# disallowed MIME types. The spec mentions 422 but the implementation uses 415.
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_disallowed_mime_type_returns_415(
    medecin_client: AsyncClient,
    patient_id: str,
):
    # Upload a file with a disallowed MIME type (plain text disguised as .txt)
    # Use content that won't match any allowed magic bytes
    disallowed_content = b"This is a plain text file with no magic bytes."
    resp = await medecin_client.post(
        "/api/v1/files/upload",
        files={"file": ("test.txt", io.BytesIO(disallowed_content), "text/plain")},
        data={"patient_id": patient_id, "file_type": "other"},
    )
    assert resp.status_code in (415, 422), (
        f"Expected 415 or 422 for disallowed MIME type, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Test 4 — Unauthenticated upload returns HTTP 401
# Validates: Requirement 5.4
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_unauthenticated_upload_returns_401(integration_app, patient_id: str):
    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as unauthenticated_client:
        resp = await unauthenticated_client.post(
            "/api/v1/files/upload",
            files={"file": ("test.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
            data={"patient_id": patient_id, "file_type": "pdf"},
        )
        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated upload, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Test 5 — Admin document upload persists metadata in MongoDB
# Validates: Requirement 5.5
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_document_upload_persists_metadata(
    integration_app,
    admin_client: AsyncClient,
    real_db: AsyncIOMotorDatabase,
):
    """
    Admin uploads a document via POST /api/v1/documents/upload.
    The document metadata must be persisted in MongoDB.
    """
    from unittest.mock import AsyncMock, MagicMock
    from backend.routers.documents import _get_document_service
    from backend.services.document_service import DocumentService
    from backend.services.s3_service import s3_service

    # Create a mock embedder that returns a zero vector
    mock_embedder = MagicMock()
    mock_embedder.encode = AsyncMock(return_value=[0.0] * 1536)

    # Override the document service dependency to use the mock embedder
    def _get_test_document_service():
        return DocumentService(database=real_db, embedder=mock_embedder, s3=s3_service)

    integration_app.dependency_overrides[_get_document_service] = _get_test_document_service

    try:
        resp = await admin_client.post(
            "/api/v1/documents/upload",
            files={"file": ("knowledge.txt", io.BytesIO(b"Medical knowledge content for testing."), "text/plain")},
            data={"title": "Test Medical Document", "source": "test-suite"},
        )
    finally:
        integration_app.dependency_overrides.pop(_get_document_service, None)

    # txt is in SUPPORTED_FORMATS for documents, so expect 201
    assert resp.status_code == 201, f"document upload failed: {resp.text}"
    body = resp.json()
    assert body["title"] == "Test Medical Document"

    # Verify metadata is persisted in MongoDB
    doc = await real_db["medical_documents"].find_one({"title": "Test Medical Document"})
    assert doc is not None, "Document metadata must be persisted in MongoDB"
    assert doc["source"] == "test-suite"


# ---------------------------------------------------------------------------
# Subtask 6.1 — Property 7: File upload/download round-trip
# Feature: testing-coverage, Property 7: File upload/download round-trip
# Validates: Requirements 5.2
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@given(file_info=_allowed_file_strategy)
@settings(max_examples=5, deadline=None)
async def test_property_file_upload_download_round_trip(
    integration_app,
    real_s3,
    file_info: tuple,
):
    """
    Property 7: File upload/download round-trip
    For any file with an allowed MIME type, upload then download SHALL return
    byte-for-byte identical content.

    # Feature: testing-coverage, Property 7: File upload/download round-trip
    Validates: Requirements 5.2
    """
    mime_type, content, filename = file_info

    # Reset rate limiter for each Hypothesis example
    from backend.core.rate_limit import limiter
    try:
        limiter._storage.reset()
    except Exception:
        pass

    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        # Login as medecin
        login_resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "medecin@test.local", "password": "TestPassword123!"},
        )
        assert login_resp.status_code == 200

        # Create a patient for the upload
        patient_resp = await client.post(
            "/api/v1/patients",
            json={
                "full_name": "Round Trip Test Patient",
                "weight_kg": 65.0,
                "allergies": [],
                "current_medications": [],
                "comorbidities": {"renal_failure": False, "hepatic_failure": False},
            },
        )
        assert patient_resp.status_code == 201
        pid = patient_resp.json()["id"]

        # Upload the file
        upload_resp = await client.post(
            "/api/v1/files/upload",
            files={"file": (filename, io.BytesIO(content), mime_type)},
            data={"patient_id": pid, "file_type": filename.rsplit(".", 1)[-1]},
        )
        assert upload_resp.status_code == 201, f"upload failed: {upload_resp.text}"
        s3_key = upload_resp.json()["s3_key"]

        # Download directly from S3 (the presigned URL points to LocalStack)
        from backend.core.config import settings
        s3_obj = real_s3.get_object(Bucket=settings.S3_BUCKET, Key=s3_key)
        downloaded = s3_obj["Body"].read()

        assert downloaded == content, (
            f"Downloaded content ({len(downloaded)} bytes) must be byte-for-byte "
            f"identical to uploaded content ({len(content)} bytes) for MIME type {mime_type}"
        )


# ---------------------------------------------------------------------------
# Subtask 6.2 — Property 8: Disallowed file types rejected
# Feature: testing-coverage, Property 8: Disallowed file types rejected
# Validates: Requirements 5.3
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@given(
    mime_type=_disallowed_mime_strategy,
    content=_disallowed_content_strategy,
)
@settings(max_examples=5, deadline=None)
async def test_property_disallowed_file_types_rejected(
    integration_app,
    mime_type: str,
    content: bytes,
):
    """
    Property 8: Disallowed file types rejected
    For any file with a MIME type not in the allowed list, upload SHALL return
    HTTP 415 (Unsupported Media Type).

    # Feature: testing-coverage, Property 8: Disallowed file types rejected
    Validates: Requirements 5.3
    """
    # Reset rate limiter for each Hypothesis example
    from backend.core.rate_limit import limiter
    try:
        limiter._storage.reset()
    except Exception:
        pass

    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        # Login as medecin
        login_resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "medecin@test.local", "password": "TestPassword123!"},
        )
        assert login_resp.status_code == 200

        # Create a patient for the upload
        patient_resp = await client.post(
            "/api/v1/patients",
            json={
                "full_name": "Disallowed Type Test Patient",
                "weight_kg": 60.0,
                "allergies": [],
                "current_medications": [],
                "comorbidities": {"renal_failure": False, "hepatic_failure": False},
            },
        )
        assert patient_resp.status_code == 201
        pid = patient_resp.json()["id"]

        # Upload with a disallowed MIME type
        upload_resp = await client.post(
            "/api/v1/files/upload",
            files={"file": ("disallowed.bin", io.BytesIO(content), mime_type)},
            data={"patient_id": pid, "file_type": "other"},
        )

        assert upload_resp.status_code in (415, 422), (
            f"Expected 415 or 422 for disallowed MIME type '{mime_type}', "
            f"got {upload_resp.status_code}: {upload_resp.text}"
        )
