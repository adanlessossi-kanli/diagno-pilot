"""
Unit tests for S3Service — Diagno-Pilot
Validates: Requirements REQ-07
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from backend.services.s3_service import S3Service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_upload_file(filename: str = "test.pdf", content: bytes = b"hello", content_type: str = "application/pdf") -> UploadFile:
    """Create a minimal UploadFile-like object for testing."""
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = filename
    mock_file.content_type = content_type
    mock_file.size = len(content)
    mock_file.read = AsyncMock(return_value=content)
    return mock_file


def _make_s3_service() -> S3Service:
    """Create an S3Service with a mocked boto3 client."""
    with patch("backend.services.s3_service.boto3.client") as mock_boto3_client:
        mock_client = MagicMock()
        mock_boto3_client.return_value = mock_client
        service = S3Service()
    service._client = mock_client
    return service


# ---------------------------------------------------------------------------
# 1. upload()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestS3ServiceUpload:
    async def test_upload_returns_correct_key_format(self):
        """S3 key must follow patients/{patient_id}/{uuid}_{filename} format."""
        service = _make_s3_service()
        service._client.put_object = MagicMock(return_value={})

        upload_file = _make_upload_file(filename="result.pdf")
        patient_id = "abc123"

        key = await service.upload(file=upload_file, patient_id=patient_id)

        assert key.startswith(f"patients/{patient_id}/")
        assert key.endswith("_result.pdf")
        # uuid part should be between the prefix and the filename
        parts = key.split("/")
        assert len(parts) == 3
        uuid_and_name = parts[2]
        assert "_" in uuid_and_name

    async def test_upload_calls_put_object(self):
        """put_object must be called exactly once with correct bucket and key."""
        service = _make_s3_service()
        service._client.put_object = MagicMock(return_value={})

        upload_file = _make_upload_file(filename="lab.csv", content=b"a,b,c")
        patient_id = "patient_xyz"

        key = await service.upload(file=upload_file, patient_id=patient_id)

        service._client.put_object.assert_called_once()
        call_kwargs = service._client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == service._bucket
        assert call_kwargs["Key"] == key
        assert call_kwargs["Body"] == b"a,b,c"

    async def test_upload_uses_content_type(self):
        """put_object must pass the file's content type."""
        service = _make_s3_service()
        service._client.put_object = MagicMock(return_value={})

        upload_file = _make_upload_file(filename="image.png", content_type="image/png")
        await service.upload(file=upload_file, patient_id="p1")

        call_kwargs = service._client.put_object.call_args.kwargs
        assert call_kwargs["ContentType"] == "image/png"

    async def test_upload_propagates_s3_exception(self):
        """If put_object raises, the exception must propagate."""
        service = _make_s3_service()
        service._client.put_object = MagicMock(side_effect=Exception("S3 unavailable"))

        upload_file = _make_upload_file()
        with pytest.raises(Exception, match="S3 unavailable"):
            await service.upload(file=upload_file, patient_id="p1")


# ---------------------------------------------------------------------------
# 2. get_presigned_url()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestS3ServicePresignedUrl:
    async def test_returns_presigned_url(self):
        """get_presigned_url must return the URL from generate_presigned_url."""
        service = _make_s3_service()
        expected_url = "https://s3.example.com/patients/p1/file.pdf?X-Amz-Signature=abc"
        service._client.generate_presigned_url = MagicMock(return_value=expected_url)

        url = await service.get_presigned_url(key="patients/p1/file.pdf")

        assert url == expected_url

    async def test_presigned_url_uses_correct_params(self):
        """generate_presigned_url must be called with correct bucket, key, and expiry."""
        service = _make_s3_service()
        service._client.generate_presigned_url = MagicMock(return_value="https://example.com/url")

        key = "patients/p1/abc_file.pdf"
        await service.get_presigned_url(key=key, expires_in=7200)

        service._client.generate_presigned_url.assert_called_once()
        call_args = service._client.generate_presigned_url.call_args
        assert call_args.args[0] == "get_object"
        assert call_args.kwargs["Params"]["Bucket"] == service._bucket
        assert call_args.kwargs["Params"]["Key"] == key
        assert call_args.kwargs["ExpiresIn"] == 7200

    async def test_presigned_url_default_expiry(self):
        """Default expiry must be 3600 seconds."""
        service = _make_s3_service()
        service._client.generate_presigned_url = MagicMock(return_value="https://example.com/url")

        await service.get_presigned_url(key="some/key")

        call_kwargs = service._client.generate_presigned_url.call_args.kwargs
        assert call_kwargs["ExpiresIn"] == 3600

    async def test_presigned_url_propagates_exception(self):
        """If generate_presigned_url raises, the exception must propagate."""
        service = _make_s3_service()
        service._client.generate_presigned_url = MagicMock(side_effect=Exception("Access denied"))

        with pytest.raises(Exception, match="Access denied"):
            await service.get_presigned_url(key="some/key")
