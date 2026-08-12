from backend.llm.groq_client import get_client
from config import settings


def transcribe_bytes(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    client = get_client()
    transcription = client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=settings.GROQ_STT_MODEL,
        temperature=settings.STT_TEMPERATURE,
        response_format="verbose_json",
    )
    return transcription.text


def transcribe_file(file_path: str) -> str:
    import os

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        audio_bytes = f.read()
    return transcribe_bytes(audio_bytes, filename)
