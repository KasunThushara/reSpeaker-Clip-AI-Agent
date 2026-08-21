from backend.tools.search import web_search
from backend.tools.calculator import calculator
from backend.tools.notion import get_notion_tools


def get_available_tools() -> list:
    """Return the tools the agent can use, based on what is configured."""
    return [web_search, calculator] + get_notion_tools()
