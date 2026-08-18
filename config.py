import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_LLM_MODEL: str = os.getenv("GROQ_LLM_MODEL", "qwen/qwen3.6-27b")
    GROQ_AGENT_MODEL: str = os.getenv("GROQ_AGENT_MODEL", "openai/gpt-oss-20b")
    GROQ_STT_MODEL: str = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
    GROQ_TTS_MODEL: str = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
    TTS_VOICE: str = os.getenv("TTS_VOICE", "autumn")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///chat.db")

    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2048
    LLM_TOP_P: float = 1.0

    STT_TEMPERATURE: float = 0.0
    STT_PROMPT: str = os.getenv("STT_PROMPT", "")
    STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "en")

    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")


settings = Settings()
