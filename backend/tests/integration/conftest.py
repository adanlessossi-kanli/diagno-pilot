"""
Integration test fixtures — session-scoped Testcontainers for MongoDB and LocalStack S3.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator, Generator

import bcrypt
import boto3
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient


# ---------------------------------------------------------------------------
# Docker availability guard
# ---------------------------------------------------------------------------

def _docker_available() -> bool:
    """Return True if a Docker daemon is reachable."""
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(items, config):
    """Skip all pytest.mark.integration tests when Docker is unavailable."""
    if not _docker_available():
        skip = pytest.mark.skip(
            reason="Docker unavailable — skipping integration tests"
        )
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# Seed helpers (mirrors scripts/seed.py logic)
# ---------------------------------------------------------------------------

_SEED_USERS = [
    {
        "email": "medecin@test.local",
        "password": "TestPassword123!",
        "full_name": "Dr. Kofi Mensah",
        "role": "medecin",
    },
    {
        "email": "admin@test.local",
        "password": "TestPassword123!",
        "full_name": "Administrateur Test",
        "role": "admin",
    },
]


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _seed_users_sync(uri: str, db_name: str) -> dict[str, dict]:
    """Insert seed users using synchronous pymongo; return mapping role → user doc."""
    client: MongoClient = MongoClient(uri)
    db = client[db_name]
    seeded: dict[str, dict] = {}
    users_col = db["users"]
    for user in _SEED_USERS:
        doc = {
            "email": user["email"],
            "password_hash": _hash_password(user["password"]),
            "full_name": user["full_name"],
            "role": user["role"],
            "locale": "fr",
            "created_at": datetime.now(timezone.utc),
            "last_login": None,
        }
        result = users_col.insert_one(doc)
        doc["_id"] = result.inserted_id
        seeded[user["role"]] = doc
    client.close()
    return seeded


# ---------------------------------------------------------------------------
# Session-scoped container fixtures (provide URIs, not Motor clients)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mongo_uri() -> Generator[tuple[str, dict, str], None, None]:
    """
    Start a mongo container via Testcontainers, seed it, and yield (uri, seeded_users).

    Requirements: 1.1, 1.3
    """
    from testcontainers.mongodb import MongoDbContainer

    image = "mongo:7.0"
    with MongoDbContainer(image) as mongo:
        uri = mongo.get_connection_url()
        db_name = "diagno_pilot_test"
        seeded = _seed_users_sync(uri, db_name)
        yield uri, seeded, db_name


@pytest.fixture(scope="session")
def real_s3() -> Generator[boto3.client, None, None]:
    """
    Start a LocalStack container via Testcontainers, create the configured S3 bucket,
    and yield a boto3 client pointed at LocalStack.

    Requirements: 1.2, 1.4
    """
    from testcontainers.localstack import LocalStackContainer

    container = LocalStackContainer(image="localstack/localstack:3.8")
    container.with_env("LOCALSTACK_ACKNOWLEDGE_ACCOUNT_REQUIREMENT", "1")
    with container as localstack:
        endpoint_url = localstack.get_url()
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-east-1",
        )

        from backend.core.config import settings
        bucket = settings.S3_BUCKET
        client.create_bucket(Bucket=bucket)

        # Expose endpoint URL for app override
        client._endpoint_url = endpoint_url  # type: ignore[attr-defined]

        yield client


# ---------------------------------------------------------------------------
# Function-scoped async fixture: real_db (Motor client per test event loop)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def reset_rate_limiter():
    """Reset the in-memory rate limiter storage before each integration test."""
    from backend.core.rate_limit import limiter
    try:
        limiter._storage.reset()
    except Exception:
        pass
    yield


@pytest_asyncio.fixture
async def real_db(mongo_uri) -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """
    Create a function-scoped AsyncIOMotorClient in the test's event loop.
    Attaches seeded_users from the session-scoped mongo_uri fixture.

    Requirements: 1.1, 1.3
    """
    uri, seeded, db_name = mongo_uri
    client: AsyncIOMotorClient = AsyncIOMotorClient(uri)
    database = client[db_name]
    database.seeded_users = seeded  # type: ignore[attr-defined]
    yield database
    client.close()


# ---------------------------------------------------------------------------
# Session-scoped integration_app fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def integration_app(mongo_uri, real_s3: boto3.client):
    """
    Return the FastAPI app with dependency overrides wiring real_db and real_s3.

    Requirements: 1.1, 1.2
    """
    from unittest.mock import MagicMock, patch

    from backend.main import app

    uri, seeded, db_name = mongo_uri

    # Create a synchronous Motor client for the session-scoped app override.
    # The mock_db_singleton.get_db() is called synchronously by the app's
    # dependency injection; we return a fresh Motor client per call.
    def _get_db_factory():
        """Return a new AsyncIOMotorDatabase each time (bound to caller's loop)."""
        client = AsyncIOMotorClient(uri)
        return client[db_name]

    mock_db_singleton = MagicMock()
    mock_db_singleton.get_db.side_effect = _get_db_factory

    # Override S3Service to use the LocalStack client
    from backend.services import s3_service as s3_module

    original_client = s3_module.s3_service._client
    original_bucket = s3_module.s3_service._bucket

    s3_module.s3_service._client = real_s3
    from backend.core.config import settings
    s3_module.s3_service._bucket = settings.S3_BUCKET

    db_patches = [
        patch("backend.routers.auth.db", mock_db_singleton),
        patch("backend.core.auth.db", mock_db_singleton),
        patch("backend.services.audit_service.db", mock_db_singleton),
        patch("backend.routers.patients.patient_service.db", mock_db_singleton),
        patch("backend.services.patient_service.db", mock_db_singleton),
        patch("backend.routers.diagnose.db", mock_db_singleton),
        patch("backend.routers.files.db", mock_db_singleton),
        patch("backend.routers.chat.db", mock_db_singleton),
        patch("backend.routers.documents.db", mock_db_singleton),
    ]

    for p in db_patches:
        p.start()

    yield app

    for p in db_patches:
        p.stop()

    # Restore original S3 client
    s3_module.s3_service._client = original_client
    s3_module.s3_service._bucket = original_bucket
