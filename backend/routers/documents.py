"""
Documents router — medical knowledge base management.
Implements REQ-05 (document indexing) and REQ-01 (admin-only write access).

Endpoints:
  POST   /api/v1/documents/upload   — admin only
  GET    /api/v1/documents
  DELETE /api/v1/documents/{id}     — admin only
  GET    /api/v1/documents/{id}/view — admin, medecin, infirmière (REQ 5.3, 5.4)
  POST   /api/v1/documents/chat     — SSE streaming document chat (REQ 7.1)
  GET    /api/v1/documents/chat/sessions — list document chat sessions (REQ 7.5)
  GET    /api/v1/documents/chat/history/{session_id} — get session messages (REQ 7.5)
  DELETE /api/v1/documents/chat/sessions/{session_id} — delete session (REQ 7.5)
  GET    /api/v1/documents/{id}/download — presigned S3 URL for download (REQ 11.2)
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.core.auth import audit_dependency, get_current_user, require_role
from backend.core.cache import cache_service
from backend.core.database import db
from backend.core.rate_limit import limiter
from backend.models.document import MedicalDocument
from backend.models.document_chat import (
    DocumentChatHistoryResponse,
    DocumentChatRequest,
    DocumentChatSessionListResponse,
    DocumentChatSessionSummary,
    DocumentDownloadResponse,
)
from backend.services.document_chat_service import DocumentChatService
from backend.services.document_service import SUPPORTED_FORMATS, DocumentService
from backend.services.embedding_model import EmbeddingModel
from backend.services.s3_service import s3_service
from backend.services.index_manager import IndexManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# ---------------------------------------------------------------------------
# Dependency — DocumentService
# ---------------------------------------------------------------------------

def _get_document_service() -> DocumentService:
    database = db.get_db()
    embedder = EmbeddingModel()
    index_manager = IndexManager(db=database)
    return DocumentService(
        database=database,
        embedder=embedder,
        s3=s3_service,
        index_manager=index_manager,
    )


# ---------------------------------------------------------------------------
# Dependency — DocumentChatService
# ---------------------------------------------------------------------------

def get_doc_chat_service(request: Request) -> DocumentChatService:
    """Return the DocumentChatService singleton stored in app.state."""
    return request.app.state.doc_chat_service


FALLBACK_WARNING = "Réponse générée par le modèle de secours (GPT-5) — vérification clinique recommandée"


# ---------------------------------------------------------------------------
# Document Chat Endpoints (must be registered before /{document_id} routes)
# ---------------------------------------------------------------------------

@router.post("/chat")
@limiter.limit("60/minute")
async def stream_document_chat(
    request: Request,
    body: DocumentChatRequest,
    current_user: dict = Depends(require_role(["admin", "medecin", "infirmière"])),
    doc_chat_service: DocumentChatService = Depends(get_doc_chat_service),
) -> EventSourceResponse:
    """POST /api/v1/documents/chat — SSE streaming Document Chat.

    Requirements: 7.1, 7.2, 7.3
    """
    session_id = body.session_id or str(uuid.uuid4())

    async def event_generator():
        async for event in doc_chat_service.send_message_stream(
            session_id=session_id,
            user_message=body.message,
            user_id=str(current_user["_id"]),
        ):
            if event.type == "token":
                yield {
                    "event": "token",
                    "data": json.dumps({"content": event.content}),
                }
            elif event.type == "done":
                sources = [s.model_dump() for s in (event.sources or [])]
                fallback_warning = FALLBACK_WARNING if event.fallback_used else None
                warnings_present = bool(fallback_warning)
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "answer": event.answer,
                        "session_id": session_id,
                        "sources": sources,
                        "llm_used": event.llm_used,
                        "fallback_warning": fallback_warning,
                        "warnings_present": warnings_present,
                    }),
                }
            elif event.type == "error":
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": event.error,
                        "retryable": event.retryable,
                    }),
                }

    return EventSourceResponse(event_generator())


@router.get(
    "/chat/sessions",
    response_model=DocumentChatSessionListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_document_chat_sessions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(require_role(["admin", "medecin", "infirmière"])),
    doc_chat_service: DocumentChatService = Depends(get_doc_chat_service),
) -> DocumentChatSessionListResponse:
    """GET /api/v1/documents/chat/sessions — List user's document chat sessions.

    Requirements: 7.5
    """
    user_id = str(current_user["_id"])
    raw_sessions = await doc_chat_service.list_sessions(user_id=user_id, skip=skip, limit=limit)

    sessions = []
    for s in raw_sessions:
        preview = None
        msgs = s.get("messages", [])
        if msgs and isinstance(msgs, list) and len(msgs) > 0:
            preview = msgs[0].get("content", "")
        sessions.append(
            DocumentChatSessionSummary(
                session_id=s["session_id"],
                created_at=str(s["created_at"]) if s.get("created_at") else None,
                updated_at=str(s["updated_at"]) if s.get("updated_at") else None,
                preview=preview,
            )
        )

    return DocumentChatSessionListResponse(sessions=sessions)


@router.get(
    "/chat/history/{session_id}",
    response_model=DocumentChatHistoryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_document_chat_history(
    session_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(require_role(["admin", "medecin", "infirmière"])),
    doc_chat_service: DocumentChatService = Depends(get_doc_chat_service),
) -> DocumentChatHistoryResponse:
    """GET /api/v1/documents/chat/history/{session_id} — Get session messages.

    Requirements: 7.5
    """
    user_id_filter = None if current_user.get("role") == "admin" else str(current_user["_id"])

    session = await doc_chat_service.get_history_paginated(
        session_id=session_id,
        user_id=user_id_filter,
        skip=skip,
        limit=limit,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document chat session not found",
        )

    return DocumentChatHistoryResponse(
        session_id=session["session_id"],
        messages=session.get("messages", []),
        total_messages=session.get("total_messages", 0),
        created_at=str(session["created_at"]) if session.get("created_at") else None,
        updated_at=str(session["updated_at"]) if session.get("updated_at") else None,
    )


@router.delete(
    "/chat/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_document_chat_session(
    session_id: str,
    current_user: dict = Depends(require_role(["admin", "medecin", "infirmière"])),
    doc_chat_service: DocumentChatService = Depends(get_doc_chat_service),
) -> None:
    """DELETE /api/v1/documents/chat/sessions/{session_id} — Delete a session.

    Requirements: 7.5
    """
    user_id_filter = None if current_user.get("role") == "admin" else str(current_user["_id"])

    deleted = await doc_chat_service.delete_session(session_id=session_id, user_id=user_id_filter)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document chat session not found",
        )


# ---------------------------------------------------------------------------
# Existing Endpoints
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


# ---------------------------------------------------------------------------
# GET /documents/{id}/download — presigned S3 URL for download (REQ 11.2)
# ---------------------------------------------------------------------------

@router.get(
    "/{document_id}/download",
    response_model=DocumentDownloadResponse,
    summary="Get a presigned S3 URL for downloading a document (admin, medecin, infirmière)",
    dependencies=[Depends(require_role(["admin", "medecin", "infirmière"]))],
)
async def download_document_file(
    document_id: str,
    svc: DocumentService = Depends(_get_document_service),
) -> DocumentDownloadResponse:
    """Return a presigned S3 URL with Content-Disposition: attachment for downloading.

    Requirements: 11.2
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

    # Extract filename from s3_key (format: patients/{id}/{uuid}_{filename})
    filename = s3_key.rsplit("/", 1)[-1] if "/" in s3_key else s3_key
    # Strip the uuid prefix if present
    if "_" in filename:
        filename = filename.split("_", 1)[1]

    # Generate presigned URL with Content-Disposition: attachment
    import asyncio
    from functools import partial

    loop = asyncio.get_event_loop()
    url: str = await loop.run_in_executor(
        None,
        partial(
            s3_service._client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": s3_service._bucket,
                "Key": s3_key,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=900,
        ),
    )

    return DocumentDownloadResponse(
        url=url,
        expires_in=900,
        filename=filename,
        content_disposition="attachment",
    )
