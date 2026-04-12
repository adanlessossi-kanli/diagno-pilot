"""Pydantic models for Document Chat and Topic Guard feedback.

Requirements: 7.1, 7.4, 11.2, 13.3
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class DocumentChatRequest(BaseModel):
    """Request body for POST /api/v1/documents/chat."""

    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None

    @field_validator("message", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class DocumentDownloadResponse(BaseModel):
    """Response for GET /api/v1/documents/{id}/download."""

    url: str
    expires_in: int = 900
    filename: str
    content_disposition: str = "attachment"


class DocumentChatSessionSummary(BaseModel):
    """Summary of a single document chat session."""

    session_id: str
    created_at: str | None = None
    updated_at: str | None = None
    preview: str | None = None


class DocumentChatSessionListResponse(BaseModel):
    """Response for GET /api/v1/documents/chat/sessions."""

    sessions: list[DocumentChatSessionSummary]


class DocumentChatHistoryResponse(BaseModel):
    """Response for GET /api/v1/documents/chat/history/{session_id}."""

    session_id: str
    messages: list[dict]
    total_messages: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class TopicGuardFeedbackRequest(BaseModel):
    """Request body for POST /api/v1/chat/feedback."""

    question: str
    response: str
