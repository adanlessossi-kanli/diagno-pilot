from fastapi import APIRouter

# TODO: Implement chat endpoints in task 13.2
# POST /api/v1/chat/message
# GET  /api/v1/chat/history/{session_id}

router = APIRouter(prefix="/chat", tags=["chat"])
