from fastapi import APIRouter

# TODO: Implement patient endpoints in tasks 7.1 and 8.1
# GET  /api/v1/patients
# POST /api/v1/patients
# GET  /api/v1/patients/{id}
# PUT  /api/v1/patients/{id}
# GET  /api/v1/patients/{id}/consultations
# POST /api/v1/patients/{id}/consultations

router = APIRouter(prefix="/patients", tags=["patients"])
