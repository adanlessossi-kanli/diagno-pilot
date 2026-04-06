"""Feedback router — POST /api/v1/feedback/retrieval (REQ 4.6, 4.7)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator

from backend.core.auth import require_role
from backend.core.database import db
from backend.core.db_metrics import timed_db_op

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

ALLOWED_ROLES = ["admin", "medecin", "infirmière"]


class RetrievalFeedbackRequest(BaseModel):
    session_id: str
    document_id: str
    chunk_id: str
    rating: int = Field(..., description="1 (positive) or -1 (negative)")

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("rating must be 1 or -1")
        return v


class RetrievalFeedbackResponse(BaseModel):
    id: str
    session_id: str
    document_id: str
    chunk_id: str
    rating: int
    timestamp: datetime


@router.post(
    "/retrieval",
    response_model=RetrievalFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Soumettre un feedback de récupération (admin, medecin, infirmière)",
)
async def submit_retrieval_feedback(
    data: RetrievalFeedbackRequest,
    current_user: dict = Depends(require_role(ALLOWED_ROLES)),
):
    """POST /api/v1/feedback/retrieval — store retrieval feedback.

    Validates rating is 1 or -1. Stores session_id, user_id, document_id,
    chunk_id, rating, and timestamp in the retrieval_feedback collection.

    Requirements: 4.6, 4.7
    """
    database = db.get_db()
    now = datetime.now(timezone.utc)
    user_id = str(current_user["_id"])

    doc = {
        "session_id": data.session_id,
        "user_id": user_id,
        "document_id": data.document_id,
        "chunk_id": data.chunk_id,
        "rating": data.rating,
        "timestamp": now,
    }

    async with timed_db_op("retrieval_feedback", "insert_one"):
        result = await database["retrieval_feedback"].insert_one(doc)

    logger.info(
        "Retrieval feedback stored: session=%r doc=%r chunk=%r rating=%d user=%s",
        data.session_id,
        data.document_id,
        data.chunk_id,
        data.rating,
        user_id,
    )

    return RetrievalFeedbackResponse(
        id=str(result.inserted_id),
        session_id=data.session_id,
        document_id=data.document_id,
        chunk_id=data.chunk_id,
        rating=data.rating,
        timestamp=now,
    )
