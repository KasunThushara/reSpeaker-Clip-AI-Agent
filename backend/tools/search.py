from langchain_core.tools import tool
from tavily import TavilyClient
from config import settings

MAX_RESULT_CHARS = 300


@tool
def web_search(query: str) -> str:
    """Search the web for current, up-to-date information. Use this for
    questions about the latest firmware, recent news, product details, or
    anything that requires live facts not in the model's training data."""
    if not settings.TAVILY_API_KEY:
        return "Web search is unavailable: TAVILY_API_KEY is not configured."

    try:
        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        response = client.search(query, max_results=3)
    except Exception as e:
        return f"Web search failed: {e}"

    results = response.get("results", [])
    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        url = r.get("url", "")
        content = r.get("content", "")[:MAX_RESULT_CHARS]
        lines.append(f"{i}. {title}\n   {url}\n   {content}")

    return "\n\n".join(lines)
