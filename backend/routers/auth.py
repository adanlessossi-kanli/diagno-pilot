from fastapi import APIRouter

# TODO: Implement auth endpoints in task 4.1
# POST /api/v1/auth/login
# POST /api/v1/auth/logout
# GET  /api/v1/auth/me

router = APIRouter(prefix="/auth", tags=["auth"])
