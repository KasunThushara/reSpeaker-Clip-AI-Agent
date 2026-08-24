import json

from flask import Blueprint, request, Response, jsonify

from backend.graph import build_graph, AgentState
from backend.graph.router import router_node
from backend.database import create_conversation, save_turn, get_recent_messages
from backend.memory import recall, save_exchange, format_memories
from backend.services import index_conversation_async
from backend.utils.text import extract_answer, strip_thinking

chat_bp = Blueprint("chat", __name__)
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def clean_stream_chunk(text: str, size: int = 40) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


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
        "memories": recall(text),
        "history": get_recent_messages(conversation_id, 10),
    }
    result = _get_graph().invoke(state)

    save_turn(conversation_id, "user", text)
    save_turn(conversation_id, "assistant", result["response"])
    save_exchange(text, result["response"])
    index_conversation_async(conversation_id)

    return jsonify({
        "response": result["response"],
        "conversation_id": conversation_id,
    })


def _stream_tokens(stream, response_box: list) -> str:
    """Consume an LLM/agent chunk stream, yielding SSE token events with thinking stripped."""
    full = ""
    last_len = 0
    for chunk in stream:
        content = getattr(chunk, "content", "") or ""
        if not content:
            continue
        full += content
        clean = strip_thinking(full)
        if len(clean) > last_len:
            yield _sse("token", {"text": clean[last_len:]})
            last_len = len(clean)
    response_box.append(full)


def _stream_simple_or_persona(text, memories, history, conversation_id, persona: bool):
    from backend.llm.client import llm
    from backend.graph.nodes.simple import SYSTEM_PROMPT as SIMPLE_PROMPT
    from backend.graph.nodes.persona import SYSTEM_PROMPT as PERSONA_PROMPT

    system_prompt = PERSONA_PROMPT if persona else SIMPLE_PROMPT
    user_content = format_memories(memories) + text
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_content},
    ]
    response_box = []
    yield from _stream_tokens(llm.stream(messages), response_box)
    response = extract_answer(response_box[0] if response_box else "")
    yield _sse("done", {"response": response, "conversation_id": conversation_id})
    save_turn(conversation_id, "user", text)
    save_turn(conversation_id, "assistant", response)
    save_exchange(text, response)
    index_conversation_async(conversation_id)


def _stream_agent(text, memories, history, conversation_id):
    from langgraph.errors import GraphRecursionError
    from backend.graph.nodes.agentic import _get_agent, MAX_AGENT_ITERATIONS

    agent = _get_agent()
    user_message = format_memories(memories) + text
    messages = [*history, ("user", user_message)]
    config = {"recursion_limit": MAX_AGENT_ITERATIONS}

    full = ""
    try:
        for state in agent.stream({"messages": messages}, config=config, stream_mode="values"):
            msgs = state.get("messages", [])
            if not msgs:
                continue
            last = msgs[-1]
            if getattr(last, "type", "") == "ai":
                for tc in getattr(last, "tool_calls", []) or []:
                    yield _sse("thinking", {"tool": tc.get("name", "")})
                content = getattr(last, "content", "") or ""
                if content:
                    full = content
    except GraphRecursionError:
        if not full:
            full = "I hit my limit while working on that. Please rephrase or ask me something simpler."

    response = extract_answer(full)
    for piece in clean_stream_chunk(response):
        yield _sse("token", {"text": piece})
    yield _sse("done", {"response": response, "conversation_id": conversation_id})
    save_turn(conversation_id, "user", text)
    save_turn(conversation_id, "assistant", response)
    save_exchange(text, response)
    index_conversation_async(conversation_id)


@chat_bp.route("/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data["text"]
    conversation_id = data.get("conversation_id") or create_conversation()
    memories = recall(text)
    history = get_recent_messages(conversation_id, 10)

    def generate():
        try:
            route = router_node({
                "messages": [],
                "transcript": text,
                "route": "",
                "response": "",
                "error": None,
                "memories": memories,
                "history": history,
            })["route"]
            if route == "context":
                yield from _stream_agent(text, memories, history, conversation_id)
            else:
                yield from _stream_simple_or_persona(
                    text, memories, history, conversation_id, persona=(route == "persona")
                )
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
