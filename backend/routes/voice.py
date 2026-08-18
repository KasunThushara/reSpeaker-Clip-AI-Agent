from flask import Blueprint, request, Response
from backend.llm import transcribe_bytes, synthesize
from backend.graph import build_graph, AgentState
from backend.database import create_conversation, save_turn

voice_bp = Blueprint("voice", __name__)
_graph = None


def _header_safe(text: str) -> str:
    return (
        text.replace("\n", " ")
        .replace("\r", "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


@voice_bp.route("/voice", methods=["POST"])
def voice():
    if "audio" not in request.files:
        return {"error": "Missing 'audio' file"}, 400

    audio_file = request.files["audio"]
    conversation_id = request.form.get("conversation_id") or create_conversation()

    audio_bytes = audio_file.read()
    transcript = transcribe_bytes(audio_bytes, audio_file.filename or "audio.wav")

    state: AgentState = {
        "messages": [],
        "transcript": transcript,
        "route": "",
        "response": "",
        "error": None,
    }
    result = _get_graph().invoke(state)

    save_turn(conversation_id, "user", transcript)
    save_turn(conversation_id, "assistant", result["response"])

    tts_audio = synthesize(result["response"])

    return Response(
        tts_audio,
        mimetype="audio/wav",
        headers={
            "X-Transcript": _header_safe(transcript),
            "X-Response": _header_safe(result["response"]),
            "X-Conversation-Id": conversation_id,
        },
    )
