from flask import Blueprint, request, jsonify
from backend.graph import build_graph, AgentState
from backend.database import create_conversation, save_turn

chat_bp = Blueprint("chat", __name__)
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


@chat_bp.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data["text"]
    conversation_id = data.get("conversation_id") or create_conversation()

    state: AgentState = {
        "messages": [],
        "transcript": text,
        "route": "",
        "response": "",
        "error": None,
    }
    result = _get_graph().invoke(state)

    save_turn(conversation_id, "user", text)
    save_turn(conversation_id, "assistant", result["response"])

    return jsonify({
        "response": result["response"],
        "conversation_id": conversation_id,
    })
