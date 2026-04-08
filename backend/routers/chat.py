"""Chat router — conversational RAG Q&A endpoints (REQ-04)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from backend.core.auth import require_role
from backend.core.rate_limit import limiter
from backend.models.document import DocumentSource
from backend.models.patient import PatientProfile
from backend.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])

FALLBACK_WARNING = "Réponse générée par le modèle de secours (GPT-5) — vérification clinique recommandée"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    patient_context: PatientProfile | None = None

    @field_validator("message", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class ChatMessageResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[DocumentSource]
    llm_used: str
    fallback_warning: str | None = None
    degraded_warning: str | None = None
    warnings_present: bool = False


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[dict]
    patient_context: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None
    total_messages: int = 0


class ChatSessionSummary(BaseModel):
    session_id: str
    created_at: str | None = None
    updated_at: str | None = None
    preview: str | None = None


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionSummary]


# ---------------------------------------------------------------------------
# Dependency: ChatService
# ---------------------------------------------------------------------------

def get_chat_service(request: Request) -> ChatService:
    """Return the ChatService singleton stored in app.state."""
    return request.app.state.chat_service


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/message",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("60/minute")
async def send_message(
    request: Request,
    body: ChatMessageRequest,
    current_user: dict = Depends(require_role(["admin", "medecin", "infirmière", "guest"])),
    chat_service: ChatService = Depends(get_chat_service),
):
    """POST /api/v1/chat/message

    Send a user message to the RAG assistant. Creates a new session if
    *session_id* is omitted. Returns the assistant answer with cited sources.
    """
    session_id, rag_response = await chat_service.send_message(
        session_id=body.session_id,
        user_message=body.message,
        patient_context=body.patient_context,
        user_id=str(current_user["_id"]),
    )

    fallback_warning = FALLBACK_WARNING if rag_response.fallback_used else None
    warnings_present = bool(fallback_warning or rag_response.degraded_warning)

    return ChatMessageResponse(
        session_id=session_id,
        answer=rag_response.answer,
        sources=rag_response.sources,
        llm_used=rag_response.llm_used,
        fallback_warning=fallback_warning,
        degraded_warning=rag_response.degraded_warning,
        warnings_present=warnings_present,
    )


@router.get(
    "/history/{session_id}",
    response_model=ChatHistoryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_chat_history(
    session_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(require_role(["admin", "medecin", "infirmière", "guest"])),
    chat_service: ChatService = Depends(get_chat_service),
):
    """GET /api/v1/chat/history/{session_id}

    Retrieve paginated message history for a chat session.
    Enforces ownership: only the session owner or an admin can access.
    """
    user_id_filter = None if current_user.get("role") == "admin" else str(current_user["_id"])

    session = await chat_service.get_history_paginated(
        session_id=session_id,
        user_id=user_id_filter,
        skip=skip,
        limit=limit,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    return ChatHistoryResponse(
        session_id=session["session_id"],
        messages=session.get("messages", []),
        patient_context=session.get("patient_context"),
        created_at=str(session["created_at"]) if session.get("created_at") else None,
        updated_at=str(session["updated_at"]) if session.get("updated_at") else None,
        total_messages=session.get("total_messages", 0),
    )


@router.get(
    "/sessions",
    response_model=ChatSessionListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_chat_sessions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(require_role(["admin", "medecin", "infirmière", "guest"])),
    chat_service: ChatService = Depends(get_chat_service),
):
    """GET /api/v1/chat/sessions

    Return the current user's chat sessions sorted by updated_at descending.
    """
    user_id = str(current_user["_id"])
    raw_sessions = await chat_service.list_sessions(user_id=user_id, skip=skip, limit=limit)

    sessions = []
    for s in raw_sessions:
        preview = None
        msgs = s.get("messages", [])
        if msgs and isinstance(msgs, list) and len(msgs) > 0:
            preview = msgs[0].get("content", "")
        sessions.append(
            ChatSessionSummary(
                session_id=s["session_id"],
                created_at=str(s["created_at"]) if s.get("created_at") else None,
                updated_at=str(s["updated_at"]) if s.get("updated_at") else None,
                preview=preview,
            )
        )

    return ChatSessionListResponse(sessions=sessions)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_chat_session(
    session_id: str,
    current_user: dict = Depends(require_role(["admin", "medecin", "infirmière", "guest"])),
    chat_service: ChatService = Depends(get_chat_service),
):
    """DELETE /api/v1/chat/sessions/{session_id}

    Delete a chat session. Only the session owner or an admin can delete.
    """
    user_id_filter = None if current_user.get("role") == "admin" else str(current_user["_id"])

    deleted = await chat_service.delete_session(session_id=session_id, user_id=user_id_filter)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    return {"detail": "Session deleted"}
