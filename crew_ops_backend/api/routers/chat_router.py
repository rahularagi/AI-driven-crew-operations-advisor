from fastapi import APIRouter
from pydantic import BaseModel

from crew_ops_backend.conversation.conversation_service import conversation_service

router = APIRouter(prefix="/chat", tags=["Conversation"])


class ChatRequest(BaseModel):
    session_id: str
    message:    str
    user_id:    str


class ChatResponse(BaseModel):
    session_id:            str
    response:              str
    mode:                  str
    requires_confirmation: bool = False


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        result = conversation_service.chat(req.session_id, req.message, req.user_id)
        return ChatResponse(**result)
    except Exception as e:
        return ChatResponse(
            session_id            = req.session_id,
            response              = f"Error: {str(e)}",
            mode                  = "QUERY",
            requires_confirmation = False,
        )
