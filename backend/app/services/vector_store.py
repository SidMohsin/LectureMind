"""
ChromaDB-backed vector store for lecture transcript chunks.

Each lecture gets its own ChromaDB collection (named by lecture_id) so
lectures are cleanly isolated from one another. Stored per chunk:
  - chunk text (document)
  - embedding
  - metadata: lecture_id, chunk_id, chunk_index, start, end
"""
from typing import List, Dict
from app.config import settings


class VectorStoreError(Exception):
    pass


_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        import chromadb
    except ImportError as e:
        raise VectorStoreError("chromadb is not installed. Run: pip install chromadb") from e
    try:
        _client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
    except Exception as e:
        raise VectorStoreError(f"Failed to initialise ChromaDB at '{settings.CHROMA_DIR}': {e}") from e
    return _client


def _collection_name(lecture_id: str) -> str:
    return f"lecture_{lecture_id}"


def index_chunks(lecture_id: str, chunks: List[Dict], embeddings: List[List[float]]) -> int:
    """
    chunks: [{"chunk_index": int, "start": float, "end": float, "text": str}, ...]
    embeddings: parallel list of embedding vectors.
    Returns number of chunks indexed.
    """
    if len(chunks) != len(embeddings):
        raise VectorStoreError("Mismatch between number of chunks and embeddings.")
    if not chunks:
        return 0

    client = _get_client()
    try:
        # Drop any pre-existing collection for this lecture (e.g. re-processing)
        try:
            client.delete_collection(_collection_name(lecture_id))
        except Exception:
            pass
        collection = client.create_collection(name=_collection_name(lecture_id))

        ids = [f"{lecture_id}_chunk_{c['chunk_index']}" for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [
            {
                "lecture_id": lecture_id,
                "chunk_index": c["chunk_index"],
                "start": c["start"],
                "end": c["end"],
            }
            for c in chunks
        ]
        collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
    except Exception as e:
        raise VectorStoreError(f"Failed to index chunks in ChromaDB: {e}") from e

    return len(chunks)


def delete_lecture_collection(lecture_id: str) -> None:
    """
    Delete the ChromaDB collection for a lecture, if it exists. This is used
    by the lecture-delete endpoint and must never raise: a lecture may never
    have reached the indexing stage (e.g. it failed earlier in the pipeline),
    or ChromaDB itself may be unavailable, and neither case should block
    deleting the lecture's metadata and files.
    """
    try:
        client = _get_client()
        client.delete_collection(_collection_name(lecture_id))
    except Exception:
        pass


def query_chunks(lecture_id: str, query_embedding: List[float], top_k: int) -> List[Dict]:
    """
    Returns list of {"chunk_id", "text", "start", "end", "score"} ordered by relevance (best first).
    score is a similarity score in [0, 1] (higher is more relevant).
    """
    client = _get_client()
    try:
        collection = client.get_collection(name=_collection_name(lecture_id))
    except Exception as e:
        raise VectorStoreError(
            f"No indexed data found for lecture '{lecture_id}'. Has processing completed? ({e})"
        ) from e

    try:
        results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    except Exception as e:
        raise VectorStoreError(f"ChromaDB retrieval failed: {e}") from e

    out = []
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for cid, doc, meta, dist in zip(ids, docs, metas, dists):
        # Chroma default distance is squared L2 on normalized embeddings; convert to a
        # similarity-like score in [0,1] for display purposes.
        similarity = max(0.0, 1.0 - (dist / 2.0))
        out.append({
            "chunk_id": cid,
            "text": doc,
            "start": meta.get("start"),
            "end": meta.get("end"),
            "score": round(float(similarity), 4),
        })
    return out
