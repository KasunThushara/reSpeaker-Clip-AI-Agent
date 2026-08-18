import time

from langchain.agents import create_agent
from groq import BadRequestError

from backend.llm.client import agent_llm
from backend.graph.state import AgentState
from backend.tools import web_search, calculator
from backend.utils.text import clean_text

SYSTEM_PROMPT = (
    "You are a helpful voice assistant with access to tools. "
    "Use web_search for current, up-to-date information. "
    "Use calculator for math. "
    "Respond in plain text only: no markdown, no asterisks, no emojis."
)

agent = create_agent(
    agent_llm,
    tools=[web_search, calculator],
    system_prompt=SYSTEM_PROMPT,
)

MAX_RETRIES = 3


def agentic_node(state: AgentState) -> dict:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            result = agent.invoke({"messages": [("user", state["transcript"])]})
            response = result["messages"][-1].content
            return {"response": clean_text(response)}
        except BadRequestError as e:
            last_error = e
            if "tool_use_failed" not in str(e) or attempt == MAX_RETRIES - 1:
                raise
            time.sleep(1)
    raise last_error
