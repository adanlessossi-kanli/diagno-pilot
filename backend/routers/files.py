from fastapi import APIRouter

# TODO: Implement file endpoints in task 8.3
# POST /api/v1/files/upload
# GET  /api/v1/files/{file_id}

router = APIRouter(prefix="/files", tags=["files"])
