"""Semantic content search across the caller's own lectures.

Metadata search is the lecture list endpoint (`GET /lectures?q=`); this endpoint adds
search by meaning: the query is embedded with the same model as the stored chunks and
ranked in PostgreSQL/pgvector by `search_lecture_content`, called with the user's own
token so only their READY lectures are searched. No LLM is involved.
"""

import logging
import time

import anyio
from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_user, get_user_db
from app.api.workspace import get_embedder
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import rate_limited
from app.core.security import AuthenticatedUser
from app.intelligence.embeddings import FastEmbedEmbedder, to_pgvector
from app.schemas.search import ContentSearch
from app.services.supabase_rest import UserScopedSupabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


def select_results(rows: list[dict], *, min_similarity: float, per_lecture: int, limit: int) -> list[dict]:
    """Best-first results above the threshold, at most `per_lecture` passages per lecture."""
    kept, counts = [], {}
    for row in sorted(rows, key=lambda r: r["similarity"], reverse=True):
        if row["similarity"] < min_similarity:
            break
        lecture_id = str(row["lecture_id"])
        if counts.get(lecture_id, 0) >= per_lecture:
            continue
        counts[lecture_id] = counts.get(lecture_id, 0) + 1
        kept.append(
            {
                "chunk_id": row["chunk_id"],
                "lecture": {
                    "id": lecture_id,
                    "title": row["lecture_title"],
                    "subject": row["lecture_subject"],
                    "topic": row["lecture_topic"],
                    "instructor": row["lecture_instructor"],
                    "lecture_date": row["lecture_date"],
                },
                "sequence": row["sequence"],
                "start_seconds": row["start_seconds"],
                "end_seconds": row["end_seconds"],
                "text": row["text"],
                "similarity": round(float(row["similarity"]), 4),
            }
        )
        if len(kept) == limit:
            break
    return kept


@router.get("/content", response_model=ContentSearch, dependencies=[Depends(rate_limited("search", "rate_limit_search"))])
async def search_content(
    q: str = Query(min_length=1, max_length=300),
    limit: int = Query(default=12, ge=1, le=30),
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
    embedder: FastEmbedEmbedder = Depends(get_embedder),
    settings: Settings = Depends(get_settings),
):
    query = " ".join(q.split())
    if len(query) < 3:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "query_too_short", "Search for at least 3 characters.")

    started = time.monotonic()
    vector = await anyio.to_thread.run_sync(embedder.embed_query, query)
    rows = await db.rpc(
        "search_lecture_content",
        {"p_query_embedding": to_pgvector(vector), "p_embedding_model": embedder.name, "p_match_count": settings.search_candidates},
    )
    results = select_results(
        rows, min_similarity=settings.search_min_similarity, per_lecture=settings.search_max_per_lecture, limit=limit
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    logger.info("search_content results=%s candidates=%s latency_ms=%s", len(results), len(rows), latency_ms)
    return {
        "query": query,
        "results": results,
        "min_similarity": settings.search_min_similarity,
        "embedding_model": embedder.name,
        "latency_ms": latency_ms,
    }
