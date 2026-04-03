"""
Documents router — medical knowledge base management.
Implements REQ-05 (document indexing) and REQ-01 (admin-only write access).

Endpoints:
  POST   /api/v1/documents/upload   — admin only
  GET    /api/v1/documents
  DELETE /api/v1/documents/{id}     — admin only
  GET    /api/v1/documents/{id}/view — admin, medecin, infirmière (REQ 5.3, 5.4)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from backend.core.auth import audit_dependency, get_current_user, require_role
from backend.core.cache import cache_service
from backend.core.database import db
from backend.models.document import MedicalDocument
from backend.services.document_service import SUPPORTED_FORMATS, DocumentService
from backend.services.embedding_service import EmbeddingModel
from backend.services.s3_service import s3_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# ---------------------------------------------------------------------------
# Dependency — DocumentService
# ---------------------------------------------------------------------------

def _get_document_service() -> DocumentService:
    database = db.get_db()
    embedder = EmbeddingModel()
    return DocumentService(database=database, embedder=embedder, s3=s3_service)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=MedicalDocument,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and index a medical document (admin and medecin)",
    dependencies=[Depends(require_role(["admin", "medecin"])), Depends(audit_dependency("upload_document", "documents"))],
)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    source: str = Form(""),
    svc: DocumentService = Depends(_get_document_service),
) -> MedicalDocument:
    """Ingest a PDF, DOCX, TXT or CSV document into the medical knowledge base."""
    filename = file.filename or ""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file format '{extension}'. Supported: {sorted(SUPPORTED_FORMATS)}",
        )

    try:
        doc = await svc.ingest(file=file, title=title, source=source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    flushed = await cache_service.flush_pattern(cache_service.make_key("rag", "*"))
    logger.info("Flushed %d RAG cache entries after document upload", flushed)

    return doc


@router.get(
    "",
    response_model=list[MedicalDocument],
    summary="List all indexed medical documents",
    dependencies=[Depends(get_current_user)],
)
async def list_documents(
    svc: DocumentService = Depends(_get_document_service),
) -> list[MedicalDocument]:
    """Return all medical documents currently indexed in the knowledge base."""
    return await svc.list_documents()


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a medical document and its chunks (admin only)",
    dependencies=[Depends(require_role(["admin"])), Depends(audit_dependency("delete_document", "documents"))],
)
async def delete_document(
    document_id: str,
    svc: DocumentService = Depends(_get_document_service),
) -> None:
    """Remove a document, all its vector chunks, and the S3 source file."""
    deleted = await svc.delete_document(document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )


# ---------------------------------------------------------------------------
# Response model for presigned URL
# ---------------------------------------------------------------------------

class DocumentViewResponse(BaseModel):
    url: str
    expires_in: int = 900  # seconds


# ---------------------------------------------------------------------------
# GET /documents/{id}/view — presigned S3 URL (REQ 5.3, 5.4)
# ---------------------------------------------------------------------------

@router.get(
    "/{document_id}/view",
    response_model=DocumentViewResponse,
    summary="Get a presigned S3 URL for viewing a document (admin, medecin, infirmière)",
    dependencies=[Depends(require_role(["admin", "medecin", "infirmière"]))],
)
async def get_document_view_url(
    document_id: str,
    svc: DocumentService = Depends(_get_document_service),
) -> DocumentViewResponse:
    """Return a presigned S3 URL valid for 15 minutes for the document's stored S3 object.

    Returns HTTP 404 if the document does not exist (REQ 5.4).
    Accessible to roles: admin, medecin, infirmière (REQ 5.3).
    """
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        oid = ObjectId(document_id)
    except (InvalidId, Exception):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    doc = await svc._docs.find_one({"_id": oid})
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    s3_key = doc.get("s3_key")
    if not s3_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' has no associated file",
        )

    # Generate presigned URL valid for 15 minutes (900 seconds)
    url = await s3_service.get_presigned_url(s3_key, expires_in=900)
    return DocumentViewResponse(url=url, expires_in=900)
