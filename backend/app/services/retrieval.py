"""
Semantic retrieval service: embeds a query and retrieves the top-k most
relevant transcript chunks for a lecture from the vector store.
"""
from typing import List, Dict
from app.services.embeddings import embed_query
from app.services.vector_store import query_chunks
from app.config import settings


def retrieve_relevant_chunks(lecture_id: str, query: str, top_k: int = None) -> List[Dict]:
    top_k = top_k or settings.TOP_K
    query_vec = embed_query(query)
    return query_chunks(lecture_id, query_vec, top_k)
