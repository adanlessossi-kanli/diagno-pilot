"""
Tests for ChunkMigrationService — LlamaIndex re-indexing migration.

Validates Requirements 14.1–14.7.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from bson import ObjectId
from llama_index.core.schema import TextNode

from backend.services.migration_service import (
    ChunkMigrationService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_doc(
    title: str = "test.pdf",
    source: str = "CHU Lomé",
    s3_key: str = "documents/abc_test.pdf",
    chunk_count: int = 3,
) -> dict:
    return {
        "_id": ObjectId(),
        "title": title,
        "source": source,
        "s3_key": s3_key,
        "chunk_count": chunk_count,
    }


def _make_text_node(text: str = "Sample chunk text", **meta) -> TextNode:
    return TextNode(text=text, metadata=meta)


@pytest_asyncio.fixture
def mock_db():
    """Fake AsyncIOMotorDatabase with medical_documents and document_chunks."""
    db = MagicMock()

    docs_col = AsyncMock()
    chunks_col = AsyncMock()

    db.__getitem__ = MagicMock(side_effect=lambda name: {
        "medical_documents": docs_col,
        "document_chunks": chunks_col,
    }[name])

    return db, docs_col, chunks_col


@pytest_asyncio.fixture
def mock_s3():
    s3 = AsyncMock()
    s3.download = AsyncMock(return_value=b"Sample document content for testing.")
    return s3


@pytest_asyncio.fixture
def mock_source_loader():
    loader = MagicMock()
    loader.load = MagicMock(return_value=[
        MagicMock(text="Chunk one about malaria.", metadata={"source": "CHU Lomé"}),
    ])
    return loader


@pytest_asyncio.fixture
def mock_chunker():
    chunker = MagicMock()
    chunker.chunk = MagicMock(return_value=[
        _make_text_node("Chunk one about malaria.", source="CHU Lomé"),
        _make_text_node("Chunk two about dengue.", source="CHU Lomé"),
    ])
    return chunker


@pytest_asyncio.fixture
def mock_index_manager():
    im = AsyncMock()
    im.insert_nodes = AsyncMock(return_value=2)
    return im


@pytest_asyncio.fixture
def mock_embedder():
    embedder = AsyncMock()
    embedder.encode = AsyncMock(return_value=[0.1] * 10)
    return embedder


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMigrateDocument:
    """Tests for single-document migration."""

    @pytest.mark.asyncio
    async def test_migrate_document_success(
        self, mock_db, mock_s3, mock_source_loader, mock_chunker, mock_index_manager, mock_embedder,
    ):
        """Req 14.1–14.5: successful migration re-indexes and updates chunk_count."""
        db, docs_col, chunks_col = mock_db
        doc = _make_doc()

        docs_col.find_one = AsyncMock(return_value=doc)
        chunks_col.find_one = AsyncMock(return_value={"metadata": {"region": "TG"}})
        chunks_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=3))
        docs_col.update_one = AsyncMock()

        service = ChunkMigrationService(
            db=db, s3=mock_s3,
            source_loader=mock_source_loader,
            semantic_chunker=mock_chunker,
            index_manager=mock_index_manager,
            embedder=mock_embedder,
        )

        result = await service.migrate_document(str(doc["_id"]))

        assert result.success is True
        assert result.new_chunk_count == 2
        assert result.old_chunk_count == 3

        # Verify old chunks were deleted
        chunks_col.delete_many.assert_called_once_with({"document_id": doc["_id"]})

        # Verify chunk_count was updated
        docs_col.update_one.assert_called_once()
        call_args = docs_col.update_one.call_args
        assert call_args[0][1] == {"$set": {"chunk_count": 2}}

    @pytest.mark.asyncio
    async def test_migrate_document_not_found(self, mock_db, mock_s3):
        """Req 14.6: returns failure for non-existent document."""
        db, docs_col, chunks_col = mock_db
        docs_col.find_one = AsyncMock(return_value=None)

        service = ChunkMigrationService(db=db, s3=mock_s3)
        result = await service.migrate_document(str(ObjectId()))

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_migrate_document_no_s3_key(self, mock_db, mock_s3):
        """Req 14.6: returns failure when document has no s3_key."""
        db, docs_col, chunks_col = mock_db
        doc = _make_doc(s3_key="")
        doc["s3_key"] = None

        docs_col.find_one = AsyncMock(return_value=doc)

        service = ChunkMigrationService(db=db, s3=mock_s3)
        result = await service.migrate_document(str(doc["_id"]))

        assert result.success is False
        assert "s3_key" in result.error.lower()

    @pytest.mark.asyncio
    async def test_migrate_document_invalid_id(self, mock_db, mock_s3):
        """Returns failure for invalid ObjectId."""
        db, docs_col, chunks_col = mock_db
        service = ChunkMigrationService(db=db, s3=mock_s3)
        result = await service.migrate_document("not-a-valid-id")

        assert result.success is False
        assert "invalid" in result.error.lower()

    @pytest.mark.asyncio
    async def test_migrate_document_s3_download_failure(
        self, mock_db, mock_s3, mock_source_loader, mock_chunker, mock_index_manager, mock_embedder,
    ):
        """Req 14.6: S3 download failure is caught and reported."""
        db, docs_col, chunks_col = mock_db
        doc = _make_doc()
        docs_col.find_one = AsyncMock(return_value=doc)
        chunks_col.find_one = AsyncMock(return_value=None)
        mock_s3.download = AsyncMock(side_effect=Exception("S3 connection refused"))

        service = ChunkMigrationService(
            db=db, s3=mock_s3,
            source_loader=mock_source_loader,
            semantic_chunker=mock_chunker,
            index_manager=mock_index_manager,
            embedder=mock_embedder,
        )
        result = await service.migrate_document(str(doc["_id"]))

        assert result.success is False
        assert "S3 connection refused" in result.error


class TestMigrateAll:
    """Tests for full migration run."""

    @pytest.mark.asyncio
    async def test_migrate_all_continues_on_failure(
        self, mock_db, mock_s3, mock_source_loader, mock_chunker, mock_index_manager, mock_embedder,
    ):
        """Req 14.6: migration continues when individual documents fail."""
        db, docs_col, chunks_col = mock_db

        good_doc = _make_doc(title="good.pdf")
        bad_doc = _make_doc(title="bad.pdf", s3_key=None)

        # find() returns cursor with to_list
        cursor_mock = AsyncMock()
        cursor_mock.to_list = AsyncMock(return_value=[good_doc, bad_doc])
        docs_col.find = MagicMock(return_value=cursor_mock)

        # For the good doc: region detection + delete + update
        chunks_col.find_one = AsyncMock(return_value=None)
        chunks_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=3))
        docs_col.update_one = AsyncMock()
        docs_col.find_one = AsyncMock(return_value=None)  # not used in migrate_all path

        service = ChunkMigrationService(
            db=db, s3=mock_s3,
            source_loader=mock_source_loader,
            semantic_chunker=mock_chunker,
            index_manager=mock_index_manager,
            embedder=mock_embedder,
        )
        report = await service.migrate_all()

        assert report.total == 2
        assert report.succeeded == 1
        assert report.failed == 1
        assert report.finished_at is not None

    @pytest.mark.asyncio
    async def test_migrate_all_empty_collection(self, mock_db, mock_s3):
        """No documents to migrate returns clean report."""
        db, docs_col, chunks_col = mock_db

        cursor_mock = AsyncMock()
        cursor_mock.to_list = AsyncMock(return_value=[])
        docs_col.find = MagicMock(return_value=cursor_mock)

        service = ChunkMigrationService(db=db, s3=mock_s3)
        report = await service.migrate_all()

        assert report.total == 0
        assert report.succeeded == 0
        assert report.failed == 0


class TestMetadataPreservation:
    """Req 14.2: migration preserves existing document metadata."""

    @pytest.mark.asyncio
    async def test_region_preserved_from_existing_chunks(
        self, mock_db, mock_s3, mock_source_loader, mock_chunker, mock_index_manager, mock_embedder,
    ):
        """Region is detected from existing chunks and passed to source loader."""
        db, docs_col, chunks_col = mock_db
        doc = _make_doc()

        docs_col.find_one = AsyncMock(return_value=doc)
        chunks_col.find_one = AsyncMock(return_value={"metadata": {"region": "BJ"}})
        chunks_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=3))
        docs_col.update_one = AsyncMock()

        service = ChunkMigrationService(
            db=db, s3=mock_s3,
            source_loader=mock_source_loader,
            semantic_chunker=mock_chunker,
            index_manager=mock_index_manager,
            embedder=mock_embedder,
        )
        await service.migrate_document(str(doc["_id"]))

        # Verify source_loader.load was called with region="BJ"
        mock_source_loader.load.assert_called_once()
        call_args = mock_source_loader.load.call_args
        assert call_args[0][3] == "BJ" or call_args.kwargs.get("region") == "BJ"

    @pytest.mark.asyncio
    async def test_region_defaults_to_all(
        self, mock_db, mock_s3, mock_source_loader, mock_chunker, mock_index_manager, mock_embedder,
    ):
        """Region defaults to ALL when no existing chunks have region metadata."""
        db, docs_col, chunks_col = mock_db
        doc = _make_doc()

        docs_col.find_one = AsyncMock(return_value=doc)
        chunks_col.find_one = AsyncMock(return_value=None)
        chunks_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        docs_col.update_one = AsyncMock()

        service = ChunkMigrationService(
            db=db, s3=mock_s3,
            source_loader=mock_source_loader,
            semantic_chunker=mock_chunker,
            index_manager=mock_index_manager,
            embedder=mock_embedder,
        )
        await service.migrate_document(str(doc["_id"]))

        call_args = mock_source_loader.load.call_args
        assert call_args[0][3] == "ALL" or call_args.kwargs.get("region") == "ALL"
