from fastapi import APIRouter
from pydantic import BaseModel

from crew_ops_backend.conversation.agent import build_graph
from crew_ops_backend.conversation.push_queue import _push_queue
from crew_ops_backend.conversation.session import get_session, save_session

router = APIRouter(prefix="/chat", tags=["Conversation"])

_graph = build_graph()


class ChatRequest(BaseModel):
    session_id: str
    message:    str
    user_id:    str   # ops controller ID — used as decided_by in action tools


class ChatResponse(BaseModel):
    session_id:            str
    response:              str
    mode:                  str   # QUERY / SIMULATE / ACTION / CONFIRM / CLARIFY
    requires_confirmation: bool = False


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    session = get_session(req.session_id)
    result  = _graph.invoke({
        "message": req.message,
        "user_id": req.user_id,
        "session": session,
    })
    save_session(req.session_id, result["session"])

    response = result.get("response", "")

    # Drain any queued push notifications and prepend them
    if _push_queue:
        pushes = "\n\n---\n".join(_push_queue)
        _push_queue.clear()
        response = f"[ALERT]\n{pushes}\n\n---\n{response}"

    return ChatResponse(
        session_id            = req.session_id,
        response              = response,
        mode                  = result.get("mode", "QUERY"),
        requires_confirmation = result.get("requires_confirmation", False),
    )
