from backend.llm.client import llm
from backend.graph.state import AgentState
from backend.utils.text import clean_text

SYSTEM_PROMPT = (
    "You are a helpful voice assistant. Keep responses concise and conversational. "
    "Respond in plain text only: no markdown, no asterisks, no emojis."
)


def simple_node(state: AgentState) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": state["transcript"]},
    ]
    response = llm.invoke(messages)
    return {"response": clean_text(response.content)}
