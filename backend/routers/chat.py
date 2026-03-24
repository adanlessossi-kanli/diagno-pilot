"""Chat router — conversational RAG Q&A endpoints (REQ-04)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.core.auth import get_current_user
from backend.core.database import db
from backend.models.document import DocumentSource, RAGResponse
from backend.models.patient import PatientProfile
from backend.services.chat_service import ChatService
from backend.services.embedding_service import EmbeddingModel
from backend.services.llm_router import LLMRouter
from backend.services.rag_service import RAGService

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    message: str
    session_id: str | None = None
    patient_context: PatientProfile | None = None


class ChatMessageResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[DocumentSource]
    llm_used: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[dict]
    patient_context: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# Dependency: ChatService
# ---------------------------------------------------------------------------

def get_chat_service() -> ChatService:
    database = db.get_db()
    mongo_client = database.client
    llm_router = LLMRouter()
    embedder = EmbeddingModel()
    rag = RAGService(
        mongo_client=mongo_client,
        llm_router=llm_router,
        embedder=embedder,
        db_name=database.name,
    )
    return ChatService(db=database, rag_service=rag)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/message",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
)
async def send_message(
    body: ChatMessageRequest,
    current_user: dict = Depends(get_current_user),
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

    return ChatMessageResponse(
        session_id=session_id,
        answer=rag_response.answer,
        sources=rag_response.sources,
        llm_used=rag_response.llm_used,
    )


@router.get(
    "/history/{session_id}",
    response_model=ChatHistoryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_chat_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """GET /api/v1/chat/history/{session_id}

    Retrieve the full message history for a chat session.
    """
    session = await chat_service.get_history(session_id)
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
    )
