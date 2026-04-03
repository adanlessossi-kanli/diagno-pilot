"""
Router medecin — Création de comptes infirmière par les médecins (RBAC Fix)

Endpoints:
  POST /api/v1/medecin/users — créer un compte infirmière (rôle medecin requis)

Requirements: 2.4, 2.9
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status

from backend.core.auth import require_role
from backend.core.database import db
from backend.core.db_metrics import timed_db_op
from backend.models.common import UserRole
from backend.routers.admin import UserCreate, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/medecin", tags=["medecin"])


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un compte infirmière (medecin uniquement)",
)
async def create_nurse(
    data: UserCreate,
    current_user: dict = Depends(require_role(["medecin"])),
):
    """POST /api/v1/medecin/users — crée un compte infirmière. Rôle medecin requis.

    Valide que le rôle demandé est strictement `infirmière` — retourne HTTP 403 sinon.

    Requirements: 2.4, 2.9
    """
    # Validate that only infirmière accounts can be created via this endpoint
    if data.role != UserRole.INFIRMIERE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="medecin can only create infirmière accounts",
        )

    database = db.get_db()

    async with timed_db_op("users", "find_one"):
        existing = await database["users"].find_one({"email": data.email})
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{data.email}' already exists",
        )

    password_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
    now = datetime.now(timezone.utc)

    doc = {
        "email": data.email,
        "password_hash": password_hash,
        "full_name": data.full_name,
        "role": data.role.value,
        "locale": data.locale,
        "is_active": True,
        "created_at": now,
    }

    async with timed_db_op("users", "insert_one"):
        result = await database["users"].insert_one(doc)
    logger.info(
        "Infirmière account '%s' created by medecin %s",
        data.email,
        str(current_user["_id"]),
    )

    return UserResponse(
        id=str(result.inserted_id),
        email=doc["email"],
        role=doc["role"],
        full_name=doc["full_name"],
        is_active=doc["is_active"],
        created_at=doc["created_at"],
    )
