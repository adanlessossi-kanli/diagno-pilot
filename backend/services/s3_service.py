"""
S3 service — file upload and presigned URL generation.
Uses boto3 (synchronous) wrapped with run_in_executor for async compatibility.
Implements REQ-07 (clinical file storage on AWS S3 / LocalStack).
"""
from __future__ import annotations

import asyncio
import uuid
from functools import partial

import boto3
from fastapi import UploadFile

from backend.core.config import settings


class S3Service:
    def __init__(self) -> None:
        kwargs: dict = {
            "region_name": settings.AWS_DEFAULT_REGION,
        }
        if settings.AWS_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL
        if settings.AWS_ACCESS_KEY_ID:
            kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        if settings.AWS_SECRET_ACCESS_KEY:
            kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

        self._client = boto3.client("s3", **kwargs)
        self._bucket = settings.S3_BUCKET

    async def upload(self, file: UploadFile, patient_id: str) -> str:
        """Upload a file to S3 and return the S3 key.

        Key format: patients/{patient_id}/{uuid}_{original_filename}
        """
        file_id = uuid.uuid4().hex
        original_name = file.filename or "unknown"
        key = f"patients/{patient_id}/{file_id}_{original_name}"

        content = await file.read()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            partial(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=file.content_type or "application/octet-stream",
            ),
        )
        return key

    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for temporary S3 access."""
        loop = asyncio.get_event_loop()
        url: str = await loop.run_in_executor(
            None,
            partial(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            ),
        )
        # LocalStack URLs use the Docker-internal hostname (e.g. http://localstack:4566)
        # which the browser can't reach. Replace with localhost for dev environments.
        if settings.AWS_ENDPOINT_URL:
            from urllib.parse import urlparse
            internal = urlparse(settings.AWS_ENDPOINT_URL)
            if internal.hostname and internal.hostname != "localhost":
                external = f"http://localhost:{internal.port or 4566}"
                url = url.replace(settings.AWS_ENDPOINT_URL, external)
        return url

    async def download(self, key: str) -> bytes:
        """Download an object from S3 and return its raw bytes."""
        loop = asyncio.get_event_loop()

        def _get() -> bytes:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()

        return await loop.run_in_executor(None, _get)


s3_service = S3Service()
