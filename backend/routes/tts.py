from flask import Blueprint, request, Response

from backend.llm import synthesize

tts_bp = Blueprint("tts", __name__)


@tts_bp.route("/tts", methods=["POST"])
def tts():
    data = request.get_json(silent=True)
    if not data or "text" not in data or not str(data["text"]).strip():
        return {"error": "Missing 'text' field"}, 400
    audio = synthesize(str(data["text"]))
    return Response(audio, mimetype="audio/wav")
