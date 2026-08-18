from backend.llm.groq_client import get_client
from backend.utils.text import clean_text
from config import settings


MAX_TTS_CHARS = 400


def _truncate(text: str, max_chars: int = MAX_TTS_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    text = text[:max_chars]
    last_period = text.rfind(".")
    last_newline = text.rfind("\n")
    cut = max(last_period, last_newline, 0)
    if cut > 0:
        text = text[: cut + 1]
    return text


def synthesize(text: str, voice: str | None = None) -> bytes:
    client = get_client()
    response = client.audio.speech.create(
        model=settings.GROQ_TTS_MODEL,
        voice=voice or settings.TTS_VOICE,
        response_format="wav",
        input=_truncate(clean_text(text)),
    )
    return response.read()


def synthesize_to_file(text: str, file_path: str, voice: str | None = None) -> None:
    client = get_client()
    response = client.audio.speech.create(
        model=settings.GROQ_TTS_MODEL,
        voice=voice or settings.TTS_VOICE,
        response_format="wav",
        input=clean_text(text),
    )
    response.stream_to_file(file_path)
