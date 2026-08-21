import logging

from mem0 import MemoryClient
from config import settings

logger = logging.getLogger(__name__)

_client = None

RECALL_SEMANTIC_THRESHOLD = 0.28
RECALL_KEYWORD_MIN_SEMANTIC = 0.24
RECALL_KEYWORD_BM25_GATE = 0.01

MEM0_CUSTOM_INSTRUCTIONS = (
    "Extract only durable, user-centric facts from this conversation. "
    "Prioritize: (1) the user's health constraints and allergies, especially anything "
    "a doctor advised (interpret doctor advice as applying to the USER, e.g. "
    "'doctor said avoid shrimp' means the user avoids shrimp); "
    "(2) the user's schedule such as meetings, appointments, and reminders; "
    "(3) the user's preferences and personal details. "
    "Do NOT store the assistant's own responses, recipes, or explanations as memories. "
    "Do NOT store transient one-off requests or questions."
)


def _get_client() -> MemoryClient:
    global _client
    if _client is None:
        _client = MemoryClient(api_key=settings.MEM0_API_KEY)
    return _client


def recall(query: str, top_k: int = 5) -> list[dict]:
    if not settings.MEM0_API_KEY:
        return []
    try:
        results = _get_client().search(
            query,
            filters={"user_id": settings.MEM0_USER_ID},
            top_k=top_k,
        )
    except Exception as e:
        logger.warning("Mem0 recall failed: %s", e)
        return []

    memories = []
    for r in results.get("results", []):
        breakdown = r.get("score_breakdown", {})
        semantic = breakdown.get("semantic", r.get("score", 0.0))
        bm25 = breakdown.get("bm25", 0.0)
        relevant = semantic >= RECALL_SEMANTIC_THRESHOLD or (
            semantic >= RECALL_KEYWORD_MIN_SEMANTIC and bm25 > RECALL_KEYWORD_BM25_GATE
        )
        memory = r.get("memory", "")
        if relevant and memory:
            memories.append({
                "text": memory,
                "created_at": (r.get("created_at") or "")[:10],
            })

    memories.sort(key=lambda m: m["created_at"], reverse=True)
    return memories


def save_exchange(user_msg: str, assistant_msg: str) -> None:
    if not settings.MEM0_API_KEY:
        return
    if not (user_msg and user_msg.strip()) or not (assistant_msg and assistant_msg.strip()):
        return
    try:
        _get_client().add(
            messages=[
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ],
            user_id=settings.MEM0_USER_ID,
            custom_instructions=MEM0_CUSTOM_INSTRUCTIONS,
        )
    except Exception as e:
        logger.warning("Mem0 save failed: %s", e)


def format_memories(memories: list) -> str:
    if not memories:
        return ""
    lines = []
    for m in memories:
        if isinstance(m, dict):
            text = m.get("text", "")
            created = m.get("created_at", "")
            lines.append(f"- {text}" + (f" (created {created})" if created else ""))
        else:
            lines.append(f"- {m}")
    return f"Relevant context from your past conversations:\n" + "\n".join(lines) + "\n\n"
