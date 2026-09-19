"""
Sentence embedding service using a local Sentence-Transformers model
(default: sentence-transformers/all-MiniLM-L6-v2). No paid API required.
"""
from typing import List
from functools import lru_cache
from app.config import settings


class EmbeddingError(Exception):
    pass


@lru_cache(maxsize=1)
def _get_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise EmbeddingError(
            "sentence-transformers is not installed. Run: pip install sentence-transformers"
        ) from e
    try:
        return SentenceTransformer(settings.EMBEDDING_MODEL)
    except Exception as e:
        raise EmbeddingError(f"Failed to load embedding model '{settings.EMBEDDING_MODEL}': {e}") from e


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    model = _get_model()
    try:
        vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
    except Exception as e:
        raise EmbeddingError(f"Embedding generation failed: {e}") from e
    return vectors.tolist()


def embed_query(query: str) -> List[float]:
    return embed_texts([query])[0]
