from backend.llm import chat
from backend.graph.state import AgentState

SYSTEM_PROMPT = "You are a helpful voice assistant. Keep responses concise and conversational."


def simple_node(state: AgentState) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": state["transcript"]},
    ]
    response = chat(messages)
    return {"response": response}
