"""
Router admin — Protocoles antibiotiques configurables (REQ 11) + Gestion des utilisateurs (RBAC)

Endpoints:
  GET    /api/v1/admin/protocols                            — liste complète avec filtre région (authentifié)
  POST   /api/v1/admin/protocols                            — création avec region scoping (rôle admin requis)
  PUT    /api/v1/admin/protocols/{id}                       — mise à jour avec region scoping (rôle admin requis)
  DELETE /api/v1/admin/protocols/{id}                       — suppression avec garde last-variant (rôle admin requis)
  GET    /api/v1/admin/protocols/{id}/version/{version_id}  — récupérer une version historique (authentifié)
  POST   /api/v1/admin/documents                            — upload document médical avec champ region requis (admin)
  GET    /api/v1/admin/users                                — liste des utilisateurs (admin)
  POST   /api/v1/admin/users                                — création d'utilisateur (admin)
  PUT    /api/v1/admin/users/{id}                           — mise à jour d'utilisateur (admin)
  GET    /api/v1/admin/stats                                — statistiques globales (admin)

Chaque modification est journalisée dans le journal d'audit avec :
  user_id, action, valeurs avant/après (REQ 11.6, 5.4)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import bcrypt
from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field

from backend.core.auth import get_current_user, require_role
from backend.core.database import db
from backend.core.db_metrics import timed_db_op
from backend.models.common import UserRole
from backend.services.alert_service import alert_service
from backend.services.audit_service import audit_service
from backend.services.prescription_service import prescription_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

_VALID_REGIONS = {"TG", "BJ", "ALL"}


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
    region: str = Field(default="ALL", description="Region scope: TG, BJ, or ALL")
    available_regions: list[str] = Field(default_factory=lambda: ["TG", "BJ"])
    atc_class: str = ""
    first_line: bool = True
    names: dict[str, str] = Field(default_factory=dict)


class AntibioticProtocolCreate(AntibioticProtocolBase):
    name: str = Field(..., description="Nom unique du protocole (lowercase)")


class AntibioticProtocolUpdate(AntibioticProtocolBase):
    pass


class AntibioticProtocol(AntibioticProtocolBase):
    name: str
    updated_by: str
    updated_at: datetime


class ProtocolVariantResponse(BaseModel):
    """Response model for a Protocol_Variant retrieved by version identifier (Requirement 11.4)."""
    name: str
    region: str = "ALL"
    available_regions: list[str] = []
    atc_class: str = ""
    first_line: bool = True
    names: dict[str, str] = {}
    paediatric_dose_per_kg: float
    adult_max_dose_mg: float
    frequency: str
    duration_days: int
    route: str
    renal_adjustment_factor: float = 1.0
    hepatic_adjustment_factor: float = 1.0
    contraindicated_age_groups: list[str] = []
    alternative: str | None = None
    version: str = ""
    created_at: str = ""


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
        region=doc.get("region", "ALL"),
        available_regions=doc.get("available_regions", ["TG", "BJ"]),
        atc_class=doc.get("atc_class", ""),
        first_line=bool(doc.get("first_line", True)),
        names=doc.get("names", {}),
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
    summary="Liste complète des protocoles antibiotiques avec filtre région optionnel",
)
async def list_protocols(
    region: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/admin/protocols — retourne les protocoles depuis MongoDB, filtrés par région si fournie.

    Requirements: 8.1, 8.3
    """
    database = db.get_db()
    query: dict[str, Any] = {}
    if region is not None:
        region_upper = region.upper()
        if region_upper not in _VALID_REGIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid region '{region}'. Must be one of: TG, BJ, ALL",
            )
        query["region"] = region_upper
    async with timed_db_op("antibiotic_protocols", "find"):
        cursor = database["antibiotic_protocols"].find(query)
        docs = await cursor.to_list(length=None)
    return [_doc_to_protocol(doc) for doc in docs]


@router.get(
    "/protocols/{protocol_id}/version/{version_id}",
    response_model=ProtocolVariantResponse,
    status_code=status.HTTP_200_OK,
    summary="Récupérer une version historique d'un protocole (Requirement 11.4)",
)
async def get_protocol_version(
    protocol_id: str,
    version_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    GET /api/v1/admin/protocols/{protocol_id}/version/{version_id}

    Retrieve a Protocol_Variant by its version identifier for audit and review.

    - `protocol_id`: the protocol name (e.g. ``amoxicillin``).
    - `version_id`: the version timestamp string stored in the ``version`` field
      (e.g. ``2025-01-15T00:00:00Z``).

    Returns HTTP 404 when no document matches the (name, version) pair.

    Requirements: 11.4
    """
    database = db.get_db()
    name = protocol_id.lower().strip()

    async with timed_db_op("antibiotic_protocols", "find_one"):
        doc = await database["antibiotic_protocols"].find_one(
            {"name": name, "version": version_id}
        )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{name}' version '{version_id}' not found",
        )

    return ProtocolVariantResponse(
        name=doc["name"],
        region=doc.get("region", "ALL"),
        available_regions=doc.get("available_regions", []),
        atc_class=doc.get("atc_class", ""),
        first_line=bool(doc.get("first_line", True)),
        names=doc.get("names", {}),
        paediatric_dose_per_kg=float(doc["paediatric_dose_per_kg"]),
        adult_max_dose_mg=float(doc["adult_max_dose_mg"]),
        frequency=doc["frequency"],
        duration_days=int(doc["duration_days"]),
        route=doc["route"],
        renal_adjustment_factor=float(doc.get("renal_adjustment_factor", 1.0)),
        hepatic_adjustment_factor=float(doc.get("hepatic_adjustment_factor", 1.0)),
        contraindicated_age_groups=doc.get("contraindicated_age_groups", []),
        alternative=doc.get("alternative"),
        version=doc.get("version", ""),
        created_at=str(doc.get("created_at", "")),
    )


@router.post(
    "/protocols",
    response_model=AntibioticProtocol,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un nouveau protocole antibiotique avec region scoping (admin)",
)
async def create_protocol(
    request: Request,
    data: AntibioticProtocolCreate,
    current_user: dict = Depends(require_role(["admin"])),
):
    """POST /api/v1/admin/protocols — crée un Protocol_Variant. Rôle admin requis.

    Requirements: 8.1, 8.3
    """
    database = db.get_db()
    name = data.name.lower().strip()
    region = data.region.upper() if data.region else "ALL"

    if region not in _VALID_REGIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid region '{region}'. Must be one of: TG, BJ, ALL",
        )

    # Vérifier l'unicité par (name, region)
    async with timed_db_op("antibiotic_protocols", "find_one"):
        existing = await database["antibiotic_protocols"].find_one({"name": name, "region": region})
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Protocol '{name}' for region '{region}' already exists",
        )

    now = datetime.now(timezone.utc)
    user_id = str(current_user["_id"])
    version_ts = now.isoformat()

    doc = {
        "name": name,
        "region": region,
        "available_regions": data.available_regions,
        "atc_class": data.atc_class,
        "first_line": data.first_line,
        "names": data.names,
        "paediatric_dose_per_kg": data.paediatric_dose_per_kg,
        "adult_max_dose_mg": data.adult_max_dose_mg,
        "frequency": data.frequency,
        "duration_days": data.duration_days,
        "route": data.route,
        "renal_adjustment_factor": data.renal_adjustment_factor,
        "hepatic_adjustment_factor": data.hepatic_adjustment_factor,
        "contraindicated_age_groups": data.contraindicated_age_groups,
        "alternative": data.alternative,
        "version": version_ts,
        "created_at": version_ts,
        "updated_by": user_id,
        "updated_at": now,
    }

    async with timed_db_op("antibiotic_protocols", "insert_one"):
        await database["antibiotic_protocols"].insert_one(doc)

    # Journal d'audit (REQ 11.6)
    ip = request.client.host if request.client else None
    await audit_service.log_action(
        user_id=user_id,
        action="create_protocol",
        resource="antibiotic_protocols",
        resource_id=f"{name}:{region}",
        details={"after": {k: v for k, v in doc.items() if k not in ("_id",)}},
        ip_address=ip,
    )

    logger.info("Protocol '%s' (region=%s) created by user %s", name, region, user_id)
    await prescription_service.reload_protocols(name)
    return _doc_to_protocol(doc)


@router.put(
    "/protocols/{name}",
    response_model=AntibioticProtocol,
    status_code=status.HTTP_200_OK,
    summary="Mettre à jour un protocole antibiotique avec region scoping (admin)",
)
async def update_protocol(
    name: str,
    request: Request,
    data: AntibioticProtocolUpdate,
    current_user: dict = Depends(require_role(["admin"])),
):
    """PUT /api/v1/admin/protocols/{name} — crée une nouvelle version du protocole.

    Accepts a `region` field in the request body to scope the update.
    Creates a new document (immutable versioning) rather than overwriting.
    Calls `prescription_service.reload_protocols(name)` synchronously before returning 200 OK.

    Requirements: 8.1, 8.2, NFR 1
    """
    database = db.get_db()
    name = name.lower().strip()
    region = data.region.upper() if data.region else "ALL"

    if region not in _VALID_REGIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid region '{region}'. Must be one of: TG, BJ, ALL",
        )

    async with timed_db_op("antibiotic_protocols", "find_one"):
        existing = await database["antibiotic_protocols"].find_one(
            {"name": name, "region": region},
            sort=[("created_at", -1)],
        )
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{name}' for region '{region}' not found",
        )

    now = datetime.now(timezone.utc)
    user_id = str(current_user["_id"])
    version_ts = now.isoformat()

    before_snapshot = {k: v for k, v in existing.items() if k not in ("_id",)}

    # Create a new version document (immutable versioning — Requirements 11.1, 11.2)
    new_doc = {
        "name": name,
        "region": region,
        "available_regions": data.available_regions,
        "atc_class": data.atc_class,
        "first_line": data.first_line,
        "names": data.names,
        "paediatric_dose_per_kg": data.paediatric_dose_per_kg,
        "adult_max_dose_mg": data.adult_max_dose_mg,
        "frequency": data.frequency,
        "duration_days": data.duration_days,
        "route": data.route,
        "renal_adjustment_factor": data.renal_adjustment_factor,
        "hepatic_adjustment_factor": data.hepatic_adjustment_factor,
        "contraindicated_age_groups": data.contraindicated_age_groups,
        "alternative": data.alternative,
        "version": version_ts,
        "created_at": version_ts,
        "updated_by": user_id,
        "updated_at": now,
    }

    async with timed_db_op("antibiotic_protocols", "insert_one"):
        await database["antibiotic_protocols"].insert_one(new_doc)

    # Journal d'audit (REQ 11.6)
    ip = request.client.host if request.client else None
    await audit_service.log_action(
        user_id=user_id,
        action="update_protocol",
        resource="antibiotic_protocols",
        resource_id=f"{name}:{region}",
        details={"before": before_snapshot, "after": {k: v for k, v in new_doc.items() if k not in ("_id",)}},
        ip_address=ip,
    )

    logger.info("Protocol '%s' (region=%s) updated by user %s (new version %s)", name, region, user_id, version_ts)
    # Synchronously reload cache before returning 200 OK (NFR 1 — within 5 s SLA)
    await prescription_service.reload_protocols(name)
    return _doc_to_protocol(new_doc)


@router.delete(
    "/protocols/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Supprimer un protocole antibiotique avec garde last-variant (admin)",
)
async def delete_protocol(
    name: str,
    request: Request,
    region: str = "ALL",
    current_user: dict = Depends(require_role(["admin"])),
):
    """DELETE /api/v1/admin/protocols/{name} — supprime un Protocol_Variant.

    Rejects deletion if the protocol is the only variant across all regions.
    Returns HTTP 409 with an explanatory error message in that case.

    Requirements: 8.5
    """
    database = db.get_db()
    name = name.lower().strip()
    region_upper = region.upper()

    if region_upper not in _VALID_REGIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid region '{region}'. Must be one of: TG, BJ, ALL",
        )

    # Check the variant to delete exists
    async with timed_db_op("antibiotic_protocols", "find_one"):
        target = await database["antibiotic_protocols"].find_one({"name": name, "region": region_upper})
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{name}' for region '{region_upper}' not found",
        )

    # Last-variant guard: count distinct regions for this antibiotic name
    async with timed_db_op("antibiotic_protocols", "distinct"):
        distinct_regions = await database["antibiotic_protocols"].distinct("region", {"name": name})

    if len(distinct_regions) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot delete protocol '{name}' (region='{region_upper}'): "
                "it is the only variant across all regions. "
                "Create a variant for another region before deleting this one."
            ),
        )

    user_id = str(current_user["_id"])
    before_snapshot = {k: v for k, v in target.items() if k not in ("_id",)}

    async with timed_db_op("antibiotic_protocols", "delete_one"):
        await database["antibiotic_protocols"].delete_one({"name": name, "region": region_upper})

    # Journal d'audit
    ip = request.client.host if request.client else None
    await audit_service.log_action(
        user_id=user_id,
        action="delete_protocol",
        resource="antibiotic_protocols",
        resource_id=f"{name}:{region_upper}",
        details={"before": before_snapshot},
        ip_address=ip,
    )

    logger.info("Protocol '%s' (region=%s) deleted by user %s", name, region_upper, user_id)
    await prescription_service.reload_protocols(name)


# ---------------------------------------------------------------------------
# Admin document upload with region field (Requirements 8.4)
# ---------------------------------------------------------------------------

class AdminDocumentResponse(BaseModel):
    id: str | None = None
    title: str
    source: str
    region: str
    chunk_count: int = 0


@router.post(
    "/documents",
    response_model=AdminDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a medical document with required region field (admin)",
)
async def upload_admin_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    source: str = Form(""),
    region: str = Form(..., description="Source region: TG, BJ, or ALL"),
    current_user: dict = Depends(require_role(["admin"])),
):
    """POST /api/v1/admin/documents — upload a medical document with a required region field.

    Validates that the region is one of TG, BJ, or ALL.
    Stores metadata.region on the resulting document_chunks documents.

    Requirements: 8.4
    """
    from backend.services.document_service import SUPPORTED_FORMATS, DocumentService
    from backend.services.embedding_service import EmbeddingModel
    from backend.services.s3_service import s3_service
    from backend.core.cache import cache_service

    region_upper = region.upper()
    if region_upper not in _VALID_REGIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid region '{region}'. Must be one of: TG, BJ, ALL",
        )

    filename = file.filename or ""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file format '{extension}'. Supported: {sorted(SUPPORTED_FORMATS)}",
        )

    database = db.get_db()
    embedder = EmbeddingModel()
    svc = DocumentService(database=database, embedder=embedder, s3=s3_service)

    try:
        doc = await svc.ingest(file=file, title=title, source=source, region=region_upper)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    flushed = await cache_service.flush_pattern(cache_service.make_key("rag", "*"))
    logger.info("Flushed %d RAG cache entries after admin document upload (region=%s)", flushed, region_upper)

    user_id = str(current_user["_id"])
    ip = request.client.host if request.client else None
    await audit_service.log_action(
        user_id=user_id,
        action="upload_document",
        resource="document_chunks",
        resource_id=doc.id,
        details={"title": doc.title, "source": doc.source, "region": region_upper},
        ip_address=ip,
        region=region_upper,
    )

    return AdminDocumentResponse(
        id=doc.id,
        title=doc.title,
        source=doc.source,
        region=region_upper,
        chunk_count=doc.chunk_count,
    )


# ---------------------------------------------------------------------------
# Drug interactions (admin)
# ---------------------------------------------------------------------------

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

    async with timed_db_op("drug_interactions", "insert_one"):
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
# New schemas for PATCH endpoints and audit log (Task 3.1)
# ---------------------------------------------------------------------------

class PatchRoleRequest(BaseModel):
    role: UserRole


class PatchStatusRequest(BaseModel):
    is_active: bool


class AuditLogResponse(BaseModel):
    id: str
    timestamp: datetime
    actor_id: str
    actor_email: str
    action: str
    resource: str
    resource_id: Optional[str] = None


class PaginatedAuditResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


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
    async with timed_db_op("users", "find"):
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

    # Self-guard: prevent admin from modifying their own account via PUT
    if user_id == str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change your own role",
        )

    async with timed_db_op("users", "find_one"):
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
        async with timed_db_op("users", "update_one"):
            await database["users"].update_one({"_id": oid}, {"$set": update_fields})

    async with timed_db_op("users", "find_one"):
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
# PATCH /users/{id}/role — role-only update with self-guard (Task 3.2)
# ---------------------------------------------------------------------------

@router.patch(
    "/users/{user_id}/role",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Mettre à jour uniquement le rôle d'un utilisateur (admin)",
)
async def patch_user_role(
    user_id: str,
    request: Request,
    data: PatchRoleRequest,
    current_user: dict = Depends(require_role(["admin"])),
):
    """PATCH /api/v1/admin/users/{id}/role — met à jour uniquement le rôle. Rôle admin requis."""
    database = db.get_db()

    # Self-guard
    if user_id == str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change your own role",
        )

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    async with timed_db_op("users", "find_one"):
        existing = await database["users"].find_one({"_id": oid})
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    async with timed_db_op("users", "update_one"):
        await database["users"].update_one({"_id": oid}, {"$set": {"role": data.role.value}})

    async with timed_db_op("users", "find_one"):
        updated = await database["users"].find_one({"_id": oid})

    ip = request.client.host if request.client else None
    admin_id = str(current_user["_id"])
    await audit_service.log_action(
        user_id=admin_id,
        action="update_user_role",
        resource="users",
        resource_id=user_id,
        details={"before": {"role": existing.get("role")}, "after": {"role": data.role.value}},
        ip_address=ip,
    )

    logger.info("User '%s' role updated to '%s' by admin %s", user_id, data.role.value, admin_id)

    return UserResponse(
        id=str(updated["_id"]),
        email=updated["email"],
        role=updated["role"],
        full_name=updated.get("full_name", ""),
        is_active=updated.get("is_active", True),
        created_at=updated.get("created_at", datetime.now(timezone.utc)),
    )


# ---------------------------------------------------------------------------
# PATCH /users/{id}/status — status-only update with self-guard (Task 3.3)
# ---------------------------------------------------------------------------

@router.patch(
    "/users/{user_id}/status",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Activer ou désactiver un utilisateur (admin)",
)
async def patch_user_status(
    user_id: str,
    request: Request,
    data: PatchStatusRequest,
    current_user: dict = Depends(require_role(["admin"])),
):
    """PATCH /api/v1/admin/users/{id}/status — met à jour uniquement is_active. Rôle admin requis."""
    database = db.get_db()

    # Self-guard: prevent admin from deactivating themselves
    if user_id == str(current_user["_id"]) and data.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot deactivate your own account",
        )

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    async with timed_db_op("users", "find_one"):
        existing = await database["users"].find_one({"_id": oid})
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    async with timed_db_op("users", "update_one"):
        await database["users"].update_one({"_id": oid}, {"$set": {"is_active": data.is_active}})

    async with timed_db_op("users", "find_one"):
        updated = await database["users"].find_one({"_id": oid})

    ip = request.client.host if request.client else None
    admin_id = str(current_user["_id"])
    await audit_service.log_action(
        user_id=admin_id,
        action="update_user_status",
        resource="users",
        resource_id=user_id,
        details={"before": {"is_active": existing.get("is_active", True)}, "after": {"is_active": data.is_active}},
        ip_address=ip,
    )

    logger.info("User '%s' status updated to is_active=%s by admin %s", user_id, data.is_active, admin_id)

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

    async with timed_db_op("users", "count_documents"):
        total_users = await database["users"].count_documents({})
    async with timed_db_op("patients", "count_documents"):
        total_patients = await database["patients"].count_documents({})

    users_by_role: dict[str, int] = {}
    for role in ["admin", "medecin", "infirmière", "guest"]:
        async with timed_db_op("users", "count_documents"):
            users_by_role[role] = await database["users"].count_documents({"role": role})

    # New fields (Task 3.4)
    try:
        async with timed_db_op("consultations", "count_documents"):
            total_consultations = await database["consultations"].count_documents({})
    except Exception:
        total_consultations = 0
    try:
        async with timed_db_op("document_chunks", "distinct"):
            distinct_doc_ids = await database["document_chunks"].distinct("document_id")
            total_documents = len(distinct_doc_ids)
    except Exception:
        total_documents = 0
    async with timed_db_op("users", "count_documents"):
        active_users = await database["users"].count_documents({"is_active": True})

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
        "totalConsultations": total_consultations,
        "totalDocuments": total_documents,
        "activeUsers": active_users,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/audit — paginated audit log (Task 3.5)
# ---------------------------------------------------------------------------

@audit_router.get(
    "",
    response_model=PaginatedAuditResponse,
    status_code=status.HTTP_200_OK,
    summary="Journal d'audit paginé (admin)",
)
async def get_audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1),
    current_user: dict = Depends(require_role(["admin"])),
):
    """GET /api/v1/audit — retourne le journal d'audit paginé. Rôle admin requis."""
    # Clamp page_size to max 100
    if page_size > 100:
        page_size = 100

    database = db.get_db()

    async with timed_db_op("audit_logs", "count_documents"):
        total = await database["audit_logs"].count_documents({})

    skip = (page - 1) * page_size
    async with timed_db_op("audit_logs", "find"):
        cursor = (
            database["audit_logs"]
            .find({})
            .sort("created_at", -1)
            .skip(skip)
            .limit(page_size)
        )
        docs = await cursor.to_list(length=page_size)

    # Resolve actor emails by joining with users collection
    items: list[AuditLogResponse] = []
    for doc in docs:
        actor_id = doc.get("user_id", "")
        actor_email = ""
        if actor_id:
            try:
                user_doc = await database["users"].find_one({"_id": ObjectId(actor_id)})
                if user_doc:
                    actor_email = user_doc.get("email", "")
            except Exception:
                pass

        items.append(
            AuditLogResponse(
                id=str(doc["_id"]),
                timestamp=doc.get("created_at", datetime.now(timezone.utc)),
                actor_id=actor_id,
                actor_email=actor_email,
                action=doc.get("action", ""),
                resource=doc.get("resource", ""),
                resource_id=doc.get("resource_id"),
            )
        )

    return PaginatedAuditResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
