from crew_ops_backend.config.settings import settings
from crew_ops_backend.conversation.push_queue import _push_queue
from crew_ops_backend.conversation.session import get_session, save_session


class ConversationService:
    def __init__(self):
        if settings.use_llm:
            from crew_ops_backend.conversation.agent_llm import build_graph
        else:
            from crew_ops_backend.conversation.agent_no_llm import build_graph
        self._graph = build_graph()

    def chat(self, session_id: str, message: str, user_id: str) -> dict:
        session = get_session(session_id)
        result  = self._graph.invoke({
            "message": message,
            "user_id": user_id,
            "session": session,
        })
        save_session(session_id, result["session"])

        response = result.get("response", "")

        if _push_queue:
            pushes = "||ALERT_SEP||".join(_push_queue)
            _push_queue.clear()
            response = f"[ALERT]\n{pushes}\n||MSG_SEP||\n{response}"

        return {
            "session_id":            session_id,
            "response":              response,
            "mode":                  result.get("mode", "QUERY"),
            "requires_confirmation": result.get("requires_confirmation", False),
        }


conversation_service = ConversationService()
