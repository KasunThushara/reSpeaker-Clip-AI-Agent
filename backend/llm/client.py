from langchain_groq import ChatGroq
from config import settings

llm = ChatGroq(
    model=settings.GROQ_LLM_MODEL,
    temperature=settings.LLM_TEMPERATURE,
    api_key=settings.GROQ_API_KEY,
)

agent_llm = ChatGroq(
    model=settings.GROQ_AGENT_MODEL,
    temperature=0.0,
    api_key=settings.GROQ_API_KEY,
)
