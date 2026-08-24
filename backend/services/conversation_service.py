import logging
import threading

from config import settings
from backend.database import get_conversation, save_conversation_summary
from backend.llm.embeddings import embed_text
from backend.vector import upsert_conversation

logger = logging.getLogger(__name__)

MIN_TURNS = 2


def _build_transcript(turns: list[dict]) -> str:
    lines = []
    for t in turns:
        role = t.get("role", "")
        content = (t.get("content", "") or "").replace("\n", " ").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _generate_summary(transcript: str) -> tuple[str, str]:
    from backend.llm.client import llm
    from backend.utils.text import strip_thinking

    prompt = (
        "Given this conversation transcript, produce a short title (max 8 words) "
        "and a one-sentence overview. Output exactly two lines:\n"
        "Title: <title>\nOverview: <overview>\n\nTranscript:\n"
        + transcript
    )
    result = llm.invoke(prompt)
    text = strip_thinking(result.content)

    title = ""
    overview = ""
    for line in text.splitlines():
        line = line.strip()
        low = line.lower()
        if low.startswith("title:"):
            title = line.split(":", 1)[1].strip()
        elif low.startswith("overview:"):
            overview = line.split(":", 1)[1].strip()

    return title or "Conversation", overview or transcript[:200]


def summarize_and_index(conversation_id: str) -> None:
    """Generate a title/overview, store it, and upsert the conversation vector."""
    if not settings.PINECONE_API_KEY:
        return

    turns = get_conversation(conversation_id)
    if len(turns) < MIN_TURNS:
        return

    transcript = _build_transcript(turns)
    title, overview = _generate_summary(transcript)
    save_conversation_summary(conversation_id, title, overview)

    vector = embed_text(f"{title}\n\n{overview}")
    upsert_conversation(
        conversation_id=conversation_id,
        user_id=settings.USER_ID,
        vector=vector,
        title=title,
    )


def index_conversation_async(conversation_id: str) -> None:
    if not settings.PINECONE_API_KEY:
        return

    def _run():
        try:
            summarize_and_index(conversation_id)
        except Exception as e:
            logger.warning("Async conversation index failed: %s", e)

    threading.Thread(target=_run, daemon=True).start()
