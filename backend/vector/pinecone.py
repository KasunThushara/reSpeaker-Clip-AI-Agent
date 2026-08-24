import logging

from config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        from pinecone import Pinecone

        _client = Pinecone(api_key=settings.PINECONE_API_KEY)
    return _client


def is_configured() -> bool:
    return bool(settings.PINECONE_API_KEY)


def init_index() -> None:
    if not is_configured():
        logger.warning("Pinecone not configured: set PINECONE_API_KEY")
        return
    try:
        from pinecone import ServerlessSpec

        pc = _get_client()
        if not pc.has_index(settings.PINECONE_INDEX_NAME):
            pc.create_index(
                name=settings.PINECONE_INDEX_NAME,
                dimension=settings.EMBEDDING_DIM,
                metric="cosine",
                spec=ServerlessSpec(cloud=settings.PINECONE_CLOUD, region=settings.PINECONE_REGION),
            )
            logger.info("Created Pinecone index %s", settings.PINECONE_INDEX_NAME)
    except Exception as e:
        logger.warning("Pinecone init_index failed: %s", e)


def upsert_conversation(
    conversation_id: str,
    user_id: str,
    vector: list[float],
    title: str,
    created_at: str = "",
) -> None:
    if not is_configured():
        return
    try:
        index = _get_client().Index(settings.PINECONE_INDEX_NAME)
        index.upsert(
            vectors=[
                {
                    "id": f"{user_id}-{conversation_id}",
                    "values": vector,
                    "metadata": {
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "title": title,
                        "created_at": created_at,
                    },
                }
            ]
        )
    except Exception as e:
        logger.warning("Pinecone upsert failed: %s", e)


def search(query_vector: list[float], user_id: str, top_k: int = 5) -> list[dict]:
    if not is_configured():
        return []
    try:
        index = _get_client().Index(settings.PINECONE_INDEX_NAME)
        res = index.query(vector=query_vector, top_k=top_k, filter={"user_id": user_id}, include_metadata=True)
        return [
            {
                "id": m["id"],
                "score": m.get("score", 0.0),
                "conversation_id": (m.get("metadata") or {}).get("conversation_id", ""),
            }
            for m in res.get("matches", [])
        ]
    except Exception as e:
        logger.warning("Pinecone search failed: %s", e)
        return []
