from flask import Blueprint, request, Response

from backend.llm import synthesize
from backend.services.audio_service import AudioService

voice_bp = Blueprint("voice", __name__)
_service = None


def _get_service():
    global _service
    if _service is None:
        _service = AudioService()
    return _service


def _header_safe(text: str) -> str:
    return (
        text.replace("\n", " ")
        .replace("\r", "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )


@voice_bp.route("/voice", methods=["POST"])
def voice():
    if "audio" not in request.files:
        return {"error": "Missing 'audio' file"}, 400

    audio_file = request.files["audio"]
    conversation_id = request.form.get("conversation_id") or None

    audio_bytes = audio_file.read()
    outcome = _get_service().process_audio(
        audio_bytes,
        audio_file.filename or "audio.wav",
        conversation_id,
    )

    tts_audio = synthesize(outcome["response"])

    return Response(
        tts_audio,
        mimetype="audio/wav",
        headers={
            "X-Transcript": _header_safe(outcome["transcript"]),
            "X-Response": _header_safe(outcome["response"]),
            "X-Conversation-Id": outcome["conversation_id"],
        },
    )
