"""
Pydantic model for refresh tokens stored in MongoDB.
"""
from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, Field


class RefreshToken(BaseModel):
    """Represents a refresh token document in the `refresh_tokens` collection."""

    token: str  # UUID opaque, unique index
    user_id: str  # ObjectId ref to users collection
    expires_at: datetime  # TTL index: 7 days
    revoked: bool = False

    model_config = {"arbitrary_types_allowed": True}
