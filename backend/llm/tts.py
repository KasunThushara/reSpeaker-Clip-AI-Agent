from backend.llm.groq_client import get_client
from config import settings


def synthesize(text: str, voice: str | None = None) -> bytes:
    client = get_client()
    response = client.audio.speech.create(
        model=settings.GROQ_TTS_MODEL,
        voice=voice or settings.TTS_VOICE,
        response_format="wav",
        input=text,
    )
    return response.read()


def synthesize_to_file(text: str, file_path: str, voice: str | None = None) -> None:
    client = get_client()
    response = client.audio.speech.create(
        model=settings.GROQ_TTS_MODEL,
        voice=voice or settings.TTS_VOICE,
        response_format="wav",
        input=text,
    )
    response.stream_to_file(file_path)
