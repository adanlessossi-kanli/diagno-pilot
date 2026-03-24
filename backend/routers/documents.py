"""
Documents router — medical knowledge base management.
Implements REQ-05 (document indexing) and REQ-01 (admin-only write access).

Endpoints:
  POST   /api/v1/documents/upload   — admin only
  GET    /api/v1/documents
  DELETE /api/v1/documents/{id}     — admin only
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from backend.core.auth import audit_dependency, get_current_user, require_role
from backend.core.database import db
from backend.models.document import MedicalDocument
from backend.services.document_service import SUPPORTED_FORMATS, DocumentService
from backend.services.embedding_service import EmbeddingModel
from backend.services.s3_service import s3_service

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
    summary="Upload and index a medical document (admin only)",
    dependencies=[Depends(require_role(["admin"])), Depends(audit_dependency("upload_document", "documents"))],
)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    source: str = Form(...),
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
