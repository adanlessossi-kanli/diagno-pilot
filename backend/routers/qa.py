"""QA router — assistant questions-réponses public (REQ 2.4, 9.2, 9.3).

Cet endpoint est accessible sans authentification (rôle guest).
Aucun token JWT n'est requis.
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from backend.core.auth import get_current_user_optional

router = APIRouter(prefix="/qa", tags=["qa"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QARequest(BaseModel):
    question: str


class QAResponse(BaseModel):
    answer: str


# ---------------------------------------------------------------------------
# Endpoint public — pas de JWT requis. Accessible aux guests.
# ---------------------------------------------------------------------------

@router.post(
    "/",
    response_model=QAResponse,
    status_code=status.HTTP_200_OK,
)
async def qa_query(
    body: QARequest,
    current_user: dict | None = Depends(get_current_user_optional),
):
    """POST /api/v1/qa

    Endpoint public — pas de JWT requis. Accessible aux guests (REQ 9.3).
    Répond à une question de l'utilisateur via l'assistant QA.
    """
    # Placeholder response — la logique RAG complète sera branchée ultérieurement
    return QAResponse(answer=f"Réponse à : {body.question}")
