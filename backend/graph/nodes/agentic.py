import time

from langchain.agents import create_agent
from groq import BadRequestError
from langgraph.errors import GraphRecursionError

from backend.llm.client import agent_llm
from backend.graph.state import AgentState
from backend.tools import get_available_tools
from backend.utils.text import extract_answer
from backend.memory import format_memories

SYSTEM_PROMPT = (
    "You are a helpful voice assistant. You use Composio as your single, "
    "unified tool layer for ALL tasks that need to read or act on external "
    "apps and services (Gmail, email, Slack, Trello, GitHub, Notion, Asana, "
    "and any other app the user names). "
    "To handle any such request, ALWAYS follow this sequence: "
    "1. Call composio_search with a short natural-language query describing "
    "   the action, to find the right tool slug and its required arguments. "
    "2. Call composio_execute with that slug and a JSON arguments string to "
    "   perform the action. "
    "3. If composio_execute reports that no account is connected, call "
    "   composio_connect with the toolkit slug. Do NOT show or mention any "
    "   URL: instead tell the user in one short sentence to click the "
    "   Connect button to authorize, and that you will continue once they "
    "   have done so. "
    "If composio_search returns no matching tools, do NOT guess or improvise: "
    "tell the user in one short sentence that no tool was found and that they "
    "should make sure the app is selected in the Tools panel. "
    "Never guess or invent a tool slug: only use slugs returned by "
    "composio_search. Run at most one search per request, do not re-search for "
    "a slug you already have, and use the minimum number of tool calls. "
    "Use the minimum number of tool calls needed; once you have enough "
    "information, answer immediately and do not call the same tool again. "
    "Respond in 2-3 short sentences maximum. "
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

MAX_RETRIES = 3
MAX_AGENT_ITERATIONS = 10

_agent = None
_tools_signature = None


def _get_agent():
    global _agent, _tools_signature
    tools = get_available_tools()
    signature = [t.name for t in tools]
    if _agent is None or signature != _tools_signature:
        _tools_signature = signature
        _agent = create_agent(
            agent_llm,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
        )
    return _agent


def agentic_node(state: AgentState) -> dict:
    user_message = format_memories(state.get("memories", [])) + state["transcript"]
    messages = [*state.get("history", []), ("user", user_message)]
    config = {"recursion_limit": MAX_AGENT_ITERATIONS}
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            result = _get_agent().invoke({"messages": messages}, config=config)
            response = result["messages"][-1].content
            return {"response": extract_answer(response)}
        except GraphRecursionError:
            return {"response": "I hit my limit while working on that. Please rephrase or ask me something simpler."}
        except BadRequestError as e:
            last_error = e
            if "tool_use_failed" not in str(e) or attempt == MAX_RETRIES - 1:
                raise
            time.sleep(1)
    raise last_error
