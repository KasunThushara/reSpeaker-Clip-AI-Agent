import logging

from langchain_core.tools import tool

from config import settings
from backend.database import get_conversations_by_ids
from backend.llm.embeddings import embed_text
from backend.vector import search as pinecone_search

logger = logging.getLogger(__name__)


@tool
def search_conversations(query: str, limit: int = 5) -> str:
    """Search the user's own past conversations for relevant discussions. Use this for
    questions about what was previously discussed or remembered from earlier chats,
    instead of web_search (which searches the internet)."""
    if not settings.PINECONE_API_KEY:
        return "Conversation search is not configured (missing PINECONE_API_KEY)."

    qvec = embed_text(query)
    matches = pinecone_search(qvec, settings.USER_ID, top_k=limit)
    if not matches:
        return "No matching past conversations found."

    conv_ids = [m["conversation_id"] or "" for m in matches if m.get("conversation_id")]
    convs = get_conversations_by_ids(conv_ids) if conv_ids else []

    lines = []
    for m in matches:
        cid = m.get("conversation_id") or ""
        conv = next((c for c in convs if c["id"] == cid), None)
        title = conv.get("title") or "(untitled)" if conv else "(untitled)"
        overview = conv.get("overview") or "" if conv else ""
        score = m.get("score", 0.0)
        lines.append(f"- {title}: {overview} (score {score:.2f})")

    return "\n".join(lines)
