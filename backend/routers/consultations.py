"""Consultations router — practitioner consultation history (REQ 11.10)."""

from fastapi import APIRouter, Depends, Query, Request, status

from backend.core.auth import require_role
from backend.core.rate_limit import limiter
from backend.models.common import PaginatedResponse
from backend.models.consultation import Consultation
from backend.services import consultation_service

router = APIRouter(prefix="/consultations", tags=["consultations"])


@router.get(
    "/me",
    response_model=PaginatedResponse[Consultation],
    status_code=status.HTTP_200_OK,
)
@limiter.limit("30/minute")
async def list_my_consultations(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(require_role(["admin", "medecin", "infirmière"])),
):
    """GET /api/v1/consultations/me — paginated consultation history for the authenticated practitioner."""
    items, total = await consultation_service.list_my_consultations(
        user_id=str(current_user["_id"]),
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse[Consultation](
        items=items, total=total, page=page, page_size=page_size,
    )
