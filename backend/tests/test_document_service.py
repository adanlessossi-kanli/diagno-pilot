"""
Unit tests for DocumentService — Diagno-Pilot
Validates: Requirements REQ-05
Tests: chunking, text extraction, embedding, S3 upload/delete, MongoDB persistence
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from bson import ObjectId
from fastapi import UploadFile

from backend.services.document_service import (
    DocumentService,
    chunk_text,
    extract_text,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    SUPPORTED_FORMATS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_upload_file(
    filename: str = "guide.txt",
    content: bytes = b"Hello world",
    content_type: str = "text/plain",
) -> UploadFile:
    mock = MagicMock(spec=UploadFile)
    mock.filename = filename
    mock.content_type = content_type
    mock.read = AsyncMock(return_value=content)
    return mock


def _make_service() -> DocumentService:
    """Build a DocumentService with fully mocked dependencies."""
    # MongoDB mocks
    mock_docs_col = MagicMock()
    mock_docs_col.insert_one = AsyncMock(return_value=MagicMock())
    mock_docs_col.update_one = AsyncMock(return_value=MagicMock())
    mock_docs_col.find_one = AsyncMock(return_value=None)
    mock_docs_col.delete_one = AsyncMock(return_value=MagicMock())
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_docs_col.find = MagicMock(return_value=mock_cursor)

    mock_chunks_col = MagicMock()
    mock_chunks_col.insert_many = AsyncMock(return_value=MagicMock())
    mock_chunks_col.delete_many = AsyncMock(return_value=MagicMock())

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(side_effect=lambda name: {
        "medical_documents": mock_docs_col,
        "document_chunks": mock_chunks_col,
    }[name])

    # Embedder mock
    mock_embedder = MagicMock()
    mock_embedder.encode = AsyncMock(return_value=[0.1] * 1536)

    # S3 mock
    mock_s3 = MagicMock()
    mock_s3._client = MagicMock()
    mock_s3._client.put_object = MagicMock(return_value={})
    mock_s3._client.delete_object = MagicMock(return_value={})
    mock_s3._bucket = "diagno-pilot-files"

    svc = DocumentService(database=mock_db, embedder=mock_embedder, s3=mock_s3)
    # Expose collections for assertions
    svc._test_docs_col = mock_docs_col
    svc._test_chunks_col = mock_chunks_col
    return svc


# ---------------------------------------------------------------------------
# 1. chunk_text
# ---------------------------------------------------------------------------

class TestChunkText:
    def test_empty_text_returns_empty_list(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_returns_single_chunk(self):
        text = "Short text."
        chunks = chunk_text(text, chunk_size=500)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_produces_multiple_chunks(self):
        text = "A" * 1200
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) > 1

    def test_chunk_size_respected(self):
        text = "B" * 2000
        chunks = chunk_text(text, chunk_size=300, overlap=0)
        for chunk in chunks:
            assert len(chunk) <= 300

    def test_overlap_creates_shared_content(self):
        # With overlap, consecutive chunks share content
        text = "X" * 200
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        # Each chunk except the last should be 100 chars
        assert len(chunks[0]) == 100
        # Second chunk starts 80 chars after first (100 - 20 overlap)
        # so they share 20 chars
        assert len(chunks) >= 2

    def test_no_empty_chunks(self):
        text = "Hello\n\n\nWorld"
        chunks = chunk_text(text, chunk_size=50, overlap=5)
        for chunk in chunks:
            assert chunk.strip() != ""

    def test_default_constants_used(self):
        text = "C" * (CHUNK_SIZE + 100)
        chunks = chunk_text(text)
        assert len(chunks) >= 2


# ---------------------------------------------------------------------------
# 2. extract_text
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_txt_extraction(self):
        content = b"Hello, world!"
        result = extract_text(content, "txt")
        assert result == "Hello, world!"

    def test_txt_utf8_decoding(self):
        content = "Héllo".encode("utf-8")
        result = extract_text(content, "txt")
        assert "H" in result

    def test_csv_extraction_produces_readable_text(self):
        content = b"name,age\nAlice,30\nBob,25"
        result = extract_text(content, "csv")
        assert "Alice" in result
        assert "Bob" in result

    def test_csv_skips_empty_rows(self):
        content = b"name,age\n\nAlice,30\n\n"
        result = extract_text(content, "csv")
        lines = [l for l in result.splitlines() if l.strip()]
        assert len(lines) == 2  # header + Alice row

    def test_unsupported_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported file format"):
            extract_text(b"data", "xlsx")

    def test_pdf_extraction_called(self):
        """PDF extraction delegates to pypdf — mock it."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "PDF content here"
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("backend.services.document_service.PdfReader", return_value=mock_reader, create=True):
            with patch.dict("sys.modules", {"pypdf": MagicMock(PdfReader=mock_reader.__class__)}):
                # Directly test the internal function
                from backend.services.document_service import _extract_text_pdf
                with patch("backend.services.document_service._extract_text_pdf", return_value="PDF content here") as mock_pdf:
                    result = extract_text(b"%PDF-1.4", "pdf")
                    mock_pdf.assert_called_once()

    def test_docx_extraction_called(self):
        """DOCX extraction delegates to python-docx — mock it."""
        from backend.services.document_service import _extract_text_docx
        with patch("backend.services.document_service._extract_text_docx", return_value="DOCX content") as mock_docx:
            result = extract_text(b"PK\x03\x04", "docx")
            mock_docx.assert_called_once()
            assert result == "DOCX content"


# ---------------------------------------------------------------------------
# 3. DocumentService.ingest
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDocumentServiceIngest:
    async def test_ingest_txt_inserts_document_record(self):
        svc = _make_service()
        file = _make_upload_file(filename="guide.txt", content=b"Medical content here.")

        doc = await svc.ingest(file=file, title="Guide", source="CHU_LOME")

        svc._test_docs_col.insert_one.assert_called_once()
        record = svc._test_docs_col.insert_one.call_args.args[0]
        assert record["title"] == "Guide"
        assert record["source"] == "CHU_LOME"
        assert record["s3_key"] is not None

    async def test_ingest_returns_medical_document(self):
        svc = _make_service()
        file = _make_upload_file(filename="protocol.txt", content=b"Protocol text.")

        doc = await svc.ingest(file=file, title="Protocol", source="OMS_AFRO")

        assert doc.title == "Protocol"
        assert doc.source == "OMS_AFRO"
        assert doc.id is not None

    async def test_ingest_uploads_to_s3(self):
        svc = _make_service()
        file = _make_upload_file(filename="doc.txt", content=b"content")

        await svc.ingest(file=file, title="Doc", source="MSF")

        svc._s3._client.put_object.assert_called_once()
        call_kwargs = svc._s3._client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "diagno-pilot-files"
        assert "documents/" in call_kwargs["Key"]

    async def test_ingest_creates_chunks(self):
        svc = _make_service()
        # Content long enough to produce multiple chunks
        content = ("Medical text. " * 100).encode()
        file = _make_upload_file(filename="long.txt", content=content)

        doc = await svc.ingest(file=file, title="Long Doc", source="PNLP")

        svc._test_chunks_col.insert_many.assert_called_once()
        chunks_inserted = svc._test_chunks_col.insert_many.call_args.args[0]
        assert len(chunks_inserted) >= 1

    async def test_ingest_embeds_each_chunk(self):
        svc = _make_service()
        content = ("Word " * 200).encode()
        file = _make_upload_file(filename="embed.txt", content=content)

        await svc.ingest(file=file, title="Embed Test", source="CHU_LOME")

        # encode called once per chunk
        assert svc._embedder.encode.call_count >= 1

    async def test_ingest_updates_chunk_count(self):
        svc = _make_service()
        file = _make_upload_file(filename="update.txt", content=b"Some text content.")

        await svc.ingest(file=file, title="Update Test", source="MSF")

        svc._test_docs_col.update_one.assert_called_once()
        update_call = svc._test_docs_col.update_one.call_args
        assert "$set" in update_call.args[1]
        assert "chunk_count" in update_call.args[1]["$set"]

    async def test_ingest_chunk_has_embedding_field(self):
        svc = _make_service()
        file = _make_upload_file(filename="chunk.txt", content=b"Chunk content here.")

        await svc.ingest(file=file, title="Chunk Test", source="CHU_LOME")

        chunks = svc._test_chunks_col.insert_many.call_args.args[0]
        for chunk in chunks:
            assert "embedding" in chunk
            assert isinstance(chunk["embedding"], list)

    async def test_ingest_csv_file(self):
        svc = _make_service()
        content = b"drug,dose\nAmoxicillin,500mg\nCiprofloxacin,250mg"
        file = _make_upload_file(filename="drugs.csv", content=content, content_type="text/csv")

        doc = await svc.ingest(file=file, title="Drug List", source="PNLP")

        assert doc.title == "Drug List"
        svc._test_chunks_col.insert_many.assert_called_once()


# ---------------------------------------------------------------------------
# 4. DocumentService.list_documents
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDocumentServiceList:
    async def test_list_returns_empty_when_no_documents(self):
        svc = _make_service()
        result = await svc.list_documents()
        assert result == []

    async def test_list_returns_documents(self):
        svc = _make_service()
        doc_id = ObjectId()
        now = datetime.now(timezone.utc)
        svc._test_docs_col.find.return_value.to_list = AsyncMock(return_value=[
            {
                "_id": doc_id,
                "title": "OMS Guide",
                "source": "OMS_AFRO",
                "s3_key": "documents/abc_guide.pdf",
                "indexed_at": now,
                "chunk_count": 10,
                "created_at": now,
            }
        ])

        result = await svc.list_documents()

        assert len(result) == 1
        assert result[0].title == "OMS Guide"
        assert result[0].source == "OMS_AFRO"
        assert result[0].chunk_count == 10
        assert result[0].id == str(doc_id)

    async def test_list_maps_all_fields(self):
        svc = _make_service()
        doc_id = ObjectId()
        now = datetime.now(timezone.utc)
        svc._test_docs_col.find.return_value.to_list = AsyncMock(return_value=[
            {
                "_id": doc_id,
                "title": "MSF Lassa",
                "source": "MSF",
                "s3_key": "documents/lassa.pdf",
                "indexed_at": now,
                "chunk_count": 5,
                "created_at": now,
            }
        ])

        result = await svc.list_documents()
        doc = result[0]

        assert doc.s3_key == "documents/lassa.pdf"
        assert doc.indexed_at == now


# ---------------------------------------------------------------------------
# 5. DocumentService.delete_document
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDocumentServiceDelete:
    async def test_delete_returns_false_for_unknown_id(self):
        svc = _make_service()
        result = await svc.delete_document(str(ObjectId()))
        assert result is False

    async def test_delete_returns_false_for_invalid_id(self):
        svc = _make_service()
        result = await svc.delete_document("not-a-valid-id")
        assert result is False

    async def test_delete_removes_document_record(self):
        svc = _make_service()
        doc_id = ObjectId()
        svc._test_docs_col.find_one = AsyncMock(return_value={
            "_id": doc_id,
            "title": "To Delete",
            "source": "CHU_LOME",
            "s3_key": "documents/abc_file.pdf",
        })

        result = await svc.delete_document(str(doc_id))

        assert result is True
        svc._test_docs_col.delete_one.assert_called_once_with({"_id": doc_id})

    async def test_delete_removes_chunks(self):
        svc = _make_service()
        doc_id = ObjectId()
        svc._test_docs_col.find_one = AsyncMock(return_value={
            "_id": doc_id,
            "title": "To Delete",
            "source": "CHU_LOME",
            "s3_key": "documents/abc_file.pdf",
        })

        await svc.delete_document(str(doc_id))

        svc._test_chunks_col.delete_many.assert_called_once_with({"document_id": doc_id})

    async def test_delete_removes_s3_file(self):
        svc = _make_service()
        doc_id = ObjectId()
        s3_key = "documents/abc_guide.pdf"
        svc._test_docs_col.find_one = AsyncMock(return_value={
            "_id": doc_id,
            "title": "To Delete",
            "source": "CHU_LOME",
            "s3_key": s3_key,
        })

        await svc.delete_document(str(doc_id))

        svc._s3._client.delete_object.assert_called_once()
        call_kwargs = svc._s3._client.delete_object.call_args.kwargs
        assert call_kwargs["Key"] == s3_key
        assert call_kwargs["Bucket"] == "diagno-pilot-files"

    async def test_delete_without_s3_key_skips_s3_deletion(self):
        svc = _make_service()
        doc_id = ObjectId()
        svc._test_docs_col.find_one = AsyncMock(return_value={
            "_id": doc_id,
            "title": "No S3",
            "source": "CHU_LOME",
            "s3_key": None,
        })

        result = await svc.delete_document(str(doc_id))

        assert result is True
        svc._s3._client.delete_object.assert_not_called()

    async def test_delete_s3_error_does_not_fail_deletion(self):
        """S3 deletion errors are swallowed — document is still removed from DB."""
        svc = _make_service()
        doc_id = ObjectId()
        svc._test_docs_col.find_one = AsyncMock(return_value={
            "_id": doc_id,
            "title": "S3 Error",
            "source": "CHU_LOME",
            "s3_key": "documents/file.pdf",
        })
        svc._s3._client.delete_object = MagicMock(side_effect=Exception("S3 down"))

        result = await svc.delete_document(str(doc_id))

        assert result is True
        svc._test_docs_col.delete_one.assert_called_once()
