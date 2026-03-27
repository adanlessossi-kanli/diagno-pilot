"""
Router admin — Protocoles antibiotiques configurables (REQ 11) + Gestion des utilisateurs (RBAC)

Endpoints:
  GET  /api/v1/admin/protocols          — liste complète (authentifié)
  POST /api/v1/admin/protocols          — création (rôle admin requis)
  PUT  /api/v1/admin/protocols/{name}   — mise à jour (rôle admin requis)
  GET  /api/v1/admin/users              — liste des utilisateurs (admin)
  POST /api/v1/admin/users              — création d'utilisateur (admin)
  PUT  /api/v1/admin/users/{id}         — mise à jour d'utilisateur (admin)
  GET  /api/v1/admin/stats              — statistiques globales (admin)

Chaque modification est journalisée dans le journal d'audit avec :
  user_id, action, valeurs avant/après (REQ 11.6, 5.4)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import bcrypt
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.core.auth import get_current_user, require_role
from backend.core.database import db
from backend.models.common import UserRole
from backend.services.alert_service import alert_service
from backend.services.audit_service import audit_service
from backend.services.prescription_service import prescription_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AntibioticProtocolBase(BaseModel):
    paediatric_dose_per_kg: float
    adult_max_dose_mg: float
    frequency: str
    duration_days: int
    route: str
    renal_adjustment_factor: float = Field(ge=0.0, le=1.0)
    hepatic_adjustment_factor: float = Field(ge=0.0, le=1.0)
    contraindicated_age_groups: list[str] = []
    alternative: str | None = None


class AntibioticProtocolCreate(AntibioticProtocolBase):
    name: str = Field(..., description="Nom unique du protocole (lowercase)")


class AntibioticProtocolUpdate(AntibioticProtocolBase):
    pass


class AntibioticProtocol(AntibioticProtocolBase):
    name: str
    updated_by: str
    updated_at: datetime


class DrugInteractionCreate(BaseModel):
    drug_a: str = Field(..., description="Premier médicament (sera converti en lowercase)")
    drug_b: str = Field(..., description="Deuxième médicament (sera converti en lowercase)")
    level: str = Field(..., pattern="^(critical|warning)$", description="Niveau d'interaction : 'critical' ou 'warning'")
    message: str = Field(..., description="Description de l'interaction")


class DrugInteractionResponse(BaseModel):
    drug_a: str
    drug_b: str
    level: str
    message: str
    created_by: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc_to_protocol(doc: dict[str, Any]) -> AntibioticProtocol:
    """Convert a MongoDB document to an AntibioticProtocol response model."""
    return AntibioticProtocol(
        name=doc["name"],
        paediatric_dose_per_kg=doc["paediatric_dose_per_kg"],
        adult_max_dose_mg=doc["adult_max_dose_mg"],
        frequency=doc["frequency"],
        duration_days=doc["duration_days"],
        route=doc["route"],
        renal_adjustment_factor=doc.get("renal_adjustment_factor", 1.0),
        hepatic_adjustment_factor=doc.get("hepatic_adjustment_factor", 1.0),
        contraindicated_age_groups=doc.get("contraindicated_age_groups", []),
        alternative=doc.get("alternative"),
        updated_by=doc.get("updated_by", ""),
        updated_at=doc.get("updated_at", datetime.now(timezone.utc)),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/protocols",
    response_model=list[AntibioticProtocol],
    status_code=status.HTTP_200_OK,
    summary="Liste complète des protocoles antibiotiques",
)
async def list_protocols(
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/admin/protocols — retourne tous les protocoles depuis MongoDB."""
    database = db.get_db()
    cursor = database["antibiotic_protocols"].find({})
    docs = await cursor.to_list(length=None)
    return [_doc_to_protocol(doc) for doc in docs]


@router.post(
    "/protocols",
    response_model=AntibioticProtocol,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un nouveau protocole antibiotique (admin)",
)
async def create_protocol(
    request: Request,
    data: AntibioticProtocolCreate,
    current_user: dict = Depends(require_role(["admin"])),
):
    """POST /api/v1/admin/protocols — crée un protocole. Rôle admin requis."""
    database = db.get_db()
    name = data.name.lower().strip()

    # Vérifier l'unicité
    existing = await database["antibiotic_protocols"].find_one({"name": name})
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Protocol '{name}' already exists",
        )

    now = datetime.now(timezone.utc)
    user_id = str(current_user["_id"])

    doc = {
        "name": name,
        "paediatric_dose_per_kg": data.paediatric_dose_per_kg,
        "adult_max_dose_mg": data.adult_max_dose_mg,
        "frequency": data.frequency,
        "duration_days": data.duration_days,
        "route": data.route,
        "renal_adjustment_factor": data.renal_adjustment_factor,
        "hepatic_adjustment_factor": data.hepatic_adjustment_factor,
        "contraindicated_age_groups": data.contraindicated_age_groups,
        "alternative": data.alternative,
        "updated_by": user_id,
        "updated_at": now,
    }

    await database["antibiotic_protocols"].insert_one(doc)

    # Journal d'audit (REQ 11.6)
    ip = request.client.host if request.client else None
    await audit_service.log_action(
        user_id=user_id,
        action="create_protocol",
        resource="antibiotic_protocols",
        resource_id=name,
        details={"after": {k: v for k, v in doc.items() if k != "_id"}},
        ip_address=ip,
    )

    logger.info("Protocol '%s' created by user %s", name, user_id)
    await prescription_service.reload_protocols()
    return _doc_to_protocol(doc)


@router.put(
    "/protocols/{name}",
    response_model=AntibioticProtocol,
    status_code=status.HTTP_200_OK,
    summary="Mettre à jour un protocole antibiotique (admin)",
)
async def update_protocol(
    name: str,
    request: Request,
    data: AntibioticProtocolUpdate,
    current_user: dict = Depends(require_role(["admin"])),
):
    """PUT /api/v1/admin/protocols/{name} — met à jour un protocole. Rôle admin requis."""
    database = db.get_db()
    name = name.lower().strip()

    existing = await database["antibiotic_protocols"].find_one({"name": name})
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{name}' not found",
        )

    now = datetime.now(timezone.utc)
    user_id = str(current_user["_id"])

    before_snapshot = {k: v for k, v in existing.items() if k not in ("_id",)}

    update_fields = {
        "paediatric_dose_per_kg": data.paediatric_dose_per_kg,
        "adult_max_dose_mg": data.adult_max_dose_mg,
        "frequency": data.frequency,
        "duration_days": data.duration_days,
        "route": data.route,
        "renal_adjustment_factor": data.renal_adjustment_factor,
        "hepatic_adjustment_factor": data.hepatic_adjustment_factor,
        "contraindicated_age_groups": data.contraindicated_age_groups,
        "alternative": data.alternative,
        "updated_by": user_id,
        "updated_at": now,
    }

    await database["antibiotic_protocols"].update_one(
        {"name": name},
        {"$set": update_fields},
    )

    after_snapshot = {"name": name, **update_fields}

    # Journal d'audit (REQ 11.6)
    ip = request.client.host if request.client else None
    await audit_service.log_action(
        user_id=user_id,
        action="update_protocol",
        resource="antibiotic_protocols",
        resource_id=name,
        details={"before": before_snapshot, "after": after_snapshot},
        ip_address=ip,
    )

    logger.info("Protocol '%s' updated by user %s", name, user_id)
    await prescription_service.reload_protocols()
    return _doc_to_protocol(after_snapshot)


@router.post(
    "/drug-interactions",
    response_model=DrugInteractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ajouter une interaction médicamenteuse (admin)",
)
async def create_drug_interaction(
    data: DrugInteractionCreate,
    current_user: dict = Depends(require_role(["admin"])),
):
    """POST /api/v1/admin/drug-interactions — ajoute une interaction. Rôle admin requis."""
    database = db.get_db()
    now = datetime.now(timezone.utc)
    user_id = str(current_user["_id"])

    doc = {
        "drug_a": data.drug_a.lower().strip(),
        "drug_b": data.drug_b.lower().strip(),
        "level": data.level,
        "message": data.message,
        "created_by": user_id,
        "created_at": now,
    }

    await database["drug_interactions"].insert_one(doc)

    logger.info(
        "Drug interaction '%s' <-> '%s' created by user %s",
        doc["drug_a"],
        doc["drug_b"],
        user_id,
    )

    await alert_service.reload_interactions()

    return DrugInteractionResponse(
        drug_a=data.drug_a.lower().strip(),
        drug_b=data.drug_b.lower().strip(),
        level=data.level,
        message=data.message,
        created_by=user_id,
        created_at=now,
    )


# ---------------------------------------------------------------------------
# User management schemas (Task 4.1)
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: UserRole = UserRole.GUEST
    locale: str = "fr"


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    role: UserRole
    full_name: str
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# User management endpoints (Task 4.1)
# ---------------------------------------------------------------------------

@router.get(
    "/users",
    response_model=list[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Liste de tous les utilisateurs (admin)",
)
async def list_users(
    current_user: dict = Depends(require_role(["admin"])),
):
    """GET /api/v1/admin/users — retourne tous les utilisateurs (sans password_hash)."""
    database = db.get_db()
    cursor = database["users"].find({}, {"password_hash": 0})
    docs = await cursor.to_list(length=None)
    return [
        UserResponse(
            id=str(doc["_id"]),
            email=doc["email"],
            role=doc["role"],
            full_name=doc.get("full_name", ""),
            is_active=doc.get("is_active", True),
            created_at=doc.get("created_at", datetime.now(timezone.utc)),
        )
        for doc in docs
    ]


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un nouvel utilisateur (admin)",
)
async def create_user(
    data: UserCreate,
    current_user: dict = Depends(require_role(["admin"])),
):
    """POST /api/v1/admin/users — crée un utilisateur. Rôle admin requis."""
    database = db.get_db()

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

    result = await database["users"].insert_one(doc)
    logger.info("User '%s' created by admin %s", data.email, str(current_user["_id"]))

    return UserResponse(
        id=str(result.inserted_id),
        email=doc["email"],
        role=doc["role"],
        full_name=doc["full_name"],
        is_active=doc["is_active"],
        created_at=doc["created_at"],
    )


@router.put(
    "/users/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Mettre à jour un utilisateur (admin)",
)
async def update_user(
    user_id: str,
    request: Request,
    data: UserUpdate,
    current_user: dict = Depends(require_role(["admin"])),
):
    """PUT /api/v1/admin/users/{id} — met à jour role/is_active. Rôle admin requis."""
    database = db.get_db()

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = await database["users"].find_one({"_id": oid})
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Capture before state (Task 4.3)
    old_role = existing.get("role")
    old_is_active = existing.get("is_active", True)

    update_fields: dict[str, Any] = {}
    if data.role is not None:
        update_fields["role"] = data.role.value
    if data.is_active is not None:
        update_fields["is_active"] = data.is_active

    if update_fields:
        await database["users"].update_one({"_id": oid}, {"$set": update_fields})

    updated = await database["users"].find_one({"_id": oid})

    new_role = updated.get("role")
    new_is_active = updated.get("is_active", True)

    # Audit log with before/after (Task 4.3)
    ip = request.client.host if request.client else None
    admin_id = str(current_user["_id"])
    await audit_service.log_action(
        user_id=admin_id,
        action="update_user_role",
        resource="users",
        resource_id=user_id,
        details={
            "before": {"role": old_role, "is_active": old_is_active},
            "after": {"role": new_role, "is_active": new_is_active},
        },
        ip_address=ip,
    )

    logger.info("User '%s' updated by admin %s", user_id, admin_id)

    return UserResponse(
        id=str(updated["_id"]),
        email=updated["email"],
        role=updated["role"],
        full_name=updated.get("full_name", ""),
        is_active=updated.get("is_active", True),
        created_at=updated.get("created_at", datetime.now(timezone.utc)),
    )


# ---------------------------------------------------------------------------
# Stats endpoint (Task 4.2)
# ---------------------------------------------------------------------------

@router.get(
    "/stats",
    status_code=status.HTTP_200_OK,
    summary="Statistiques globales (admin)",
)
async def get_stats(
    request: Request,
    current_user: dict = Depends(require_role(["admin"])),
):
    """GET /api/v1/admin/stats — retourne les statistiques globales. Rôle admin requis."""
    database = db.get_db()

    total_users = await database["users"].count_documents({})
    total_patients = await database["patients"].count_documents({})

    users_by_role: dict[str, int] = {}
    for role in ["admin", "medecin", "infirmière", "guest"]:
        users_by_role[role] = await database["users"].count_documents({"role": role})

    # Audit log (Task 4.2)
    ip = request.client.host if request.client else None
    await audit_service.log_action(
        user_id=str(current_user["_id"]),
        action="view_stats",
        resource="admin_stats",
        ip_address=ip,
    )

    return {
        "total_users": total_users,
        "users_by_role": users_by_role,
        "total_patients": total_patients,
    }
