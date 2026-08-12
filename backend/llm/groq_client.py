from groq import Groq
from config import settings

_client = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    client = get_client()
    completion = client.chat.completions.create(
        model=model or settings.GROQ_LLM_MODEL,
        messages=messages,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        max_completion_tokens=max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS,
        top_p=settings.LLM_TOP_P,
        stream=False,
    )
    return completion.choices[0].message.content
