import logging

from config import settings

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s...", settings.EMBEDDING_MODEL)
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _model


def embed_text(text: str) -> list[float]:
    if not text.strip():
        return [0.0] * settings.EMBEDDING_DIM
    vector = _get_model().encode(text, normalize_embeddings=True)
    return vector.tolist()
