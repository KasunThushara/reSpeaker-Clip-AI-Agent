from backend.llm.client import llm
from backend.graph.state import AgentState
from backend.utils.text import strip_thinking

ROUTER_PROMPT = """You are a routing classifier.

Classify the user question into exactly ONE of these categories:

simple
context
persona

Rules:

simple:
- General questions
- Explanations
- Normal conversations
- No external tools or special personality required

context:
- Questions that may require external information
- Questions that may eventually require tools, search, database access,
  device information, or other contextual information

persona:
- The user explicitly requests a style, personality, teaching style,
  role, or special behavior

Return ONLY one word:
simple
context
persona

User question:
"""

VALID_ROUTES = {"simple", "context", "persona"}


def router_node(state: AgentState) -> dict:
    question = state["transcript"]
    result = llm.invoke(ROUTER_PROMPT + question)
    route = strip_thinking(result.content).strip().lower()

    if route not in VALID_ROUTES:
        route = "simple"

    return {"route": route}
