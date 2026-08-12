import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_LLM_MODEL: str = os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
    GROQ_STT_MODEL: str = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
    GROQ_TTS_MODEL: str = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
    TTS_VOICE: str = os.getenv("TTS_VOICE", "autumn")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///chat.db")

    LLM_TEMPERATURE: float = 1.0
    LLM_MAX_TOKENS: int = 2048
    LLM_TOP_P: float = 1.0

    STT_TEMPERATURE: float = 0.0


settings = Settings()
