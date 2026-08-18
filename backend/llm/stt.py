import re
from difflib import get_close_matches

from backend.llm.groq_client import get_client
from config import settings

STT_CORRECTIONS = {
    "xperia 3800": "XVF3800",
    "xperia3800": "XVF3800",
    "xvf 3800": "XVF3800",
    "xvf3800": "XVF3800",
    "xpm 3800": "XVF3800",
    "xpm3800": "XVF3800",
    "i squared s": "I2S",
    "i2s": "I2S",
    "aids 2": "I2S",
    "aids to": "I2S",
    "free speaker": "reSpeaker",
    "seed studio": "Seeed Studio",
}

DOMAIN_TERMS = [
    "XVF3800",
    "XMOS",
    "reSpeaker",
    "I2S",
    "TDM",
    "USB",
    "DFU",
    "DSP",
    "GPIO",
    "ESP32",
]

_TERM_LOOKUP = {t.lower(): t for t in DOMAIN_TERMS}

FUZZY_CUTOFF = 0.85
FUZZY_MIN_LEN = 4


def _fuzzy_correct(text: str) -> str:
    words = text.split()
    result = []
    for word in words:
        if len(word) >= FUZZY_MIN_LEN:
            matches = get_close_matches(
                word.lower(), list(_TERM_LOOKUP.keys()), n=1, cutoff=FUZZY_CUTOFF
            )
            if matches and word.lower() != matches[0]:
                result.append(_TERM_LOOKUP[matches[0]])
                continue
        result.append(word)
    return " ".join(result)


def _apply_corrections(text: str) -> str:
    corrected = text
    for wrong, right in STT_CORRECTIONS.items():
        corrected = re.sub(re.escape(wrong), right, corrected, flags=re.IGNORECASE)
    return _fuzzy_correct(corrected)


def transcribe_bytes(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    client = get_client()
    transcription = client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=settings.GROQ_STT_MODEL,
        temperature=settings.STT_TEMPERATURE,
        response_format="verbose_json",
        prompt=settings.STT_PROMPT or None,
        language=settings.STT_LANGUAGE or None,
    )
    return _apply_corrections(transcription.text)


def transcribe_file(file_path: str) -> str:
    import os

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        audio_bytes = f.read()
    return transcribe_bytes(audio_bytes, filename)
