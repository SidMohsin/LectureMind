"""Sentence embeddings behind a small interface, implemented with fastembed.

fastembed runs sentence-embedding models on ONNX Runtime (no PyTorch). Passages
(lecture chunks) and queries are embedded differently where the model expects
it (BGE models use a query instruction). The model name and dimension are
stored with every vector so incompatible vectors are never mixed; changing the
model means re-embedding.
"""

import threading
from typing import Protocol

from app.core.config import Settings


class Embedder(Protocol):
    name: str
    dimension: int

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


_models: dict[str, object] = {}
_lock = threading.Lock()


class FastEmbedEmbedder:
    def __init__(self, settings: Settings):
        self.name = settings.embedding_model
        self.dimension = settings.embedding_dimension
        self.cache_dir = settings.model_cache_path / "embeddings"

    def _model(self):
        from fastembed import TextEmbedding

        with _lock:
            if self.name not in _models:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                _models[self.name] = TextEmbedding(model_name=self.name, cache_dir=str(self.cache_dir))
            return _models[self.name]

    def _check(self, vectors: list[list[float]]) -> list[list[float]]:
        for vector in vectors:
            if len(vector) != self.dimension:
                raise ValueError(f"{self.name} produced {len(vector)} dimensions, expected {self.dimension}.")
        return vectors

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._check([vector.tolist() for vector in self._model().passage_embed(texts)])

    def embed_query(self, text: str) -> list[float]:
        return self._check([vector.tolist() for vector in self._model().query_embed([text])])[0]


def to_pgvector(vector: list[float]) -> str:
    """pgvector's text format, accepted through the REST API."""
    return "[" + ",".join(f"{value:.7g}" for value in vector) + "]"
