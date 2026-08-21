from backend.llm.client import llm
from backend.graph.state import AgentState
from backend.utils.text import extract_answer
from backend.memory import format_memories

SYSTEM_PROMPT = (
    "You are a helpful voice assistant. Respond in 2-3 short sentences maximum. "
    "Respond in plain text only: no markdown, no asterisks, no emojis. "
    "Your message may include recalled context from past conversations. Use it only when "
    "it is directly relevant to the user's request topic: mention a scheduling conflict "
    "only when they discuss their schedule, and a health or dietary constraint only when "
    "they discuss food. Never mix unrelated topics: do not mention food or allergies when "
    "the user talks about meetings, and do not mention meetings when they talk about food. "
    "If recalled memories conflict, trust the most recently created one. "
    "When the user states a new fact or asks you to remember something, acknowledge ONLY "
    "that fact. Do NOT mention, repeat, or confirm any other recalled memories that are "
    "unrelated to what they just said."
)


def simple_node(state: AgentState) -> dict:
    user_content = format_memories(state.get("memories", [])) + state["transcript"]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *state.get("history", []),
        {"role": "user", "content": user_content},
    ]
    response = llm.invoke(messages)
    return {"response": extract_answer(response.content)}
