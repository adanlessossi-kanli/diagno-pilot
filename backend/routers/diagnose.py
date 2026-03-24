from fastapi import APIRouter

# TODO: Implement diagnose endpoints in tasks 10.2 and 11.3
# POST /api/v1/diagnose/symptoms
# POST /api/v1/diagnose/prescription
# GET  /api/v1/diagnose/session/{session_id}

router = APIRouter(prefix="/diagnose", tags=["diagnose"])
