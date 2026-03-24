from fastapi import APIRouter

# TODO: Implement document endpoints in task 14.2
# POST   /api/v1/documents/upload
# GET    /api/v1/documents
# DELETE /api/v1/documents/{id}

router = APIRouter(prefix="/documents", tags=["documents"])
