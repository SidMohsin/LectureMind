"""Lecture workspace: transcript + intelligence, private media playback, grounded Q&A.

Every endpoint first loads the lecture with the caller's own token and user id, so a
lecture that doesn't exist and one owned by someone else are indistinguishable (404).
All later reads also go through the user-scoped client, so RLS applies to them too.
Only chat-log inserts use the service role, after ownership has been verified.
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.api.deps import get_current_user, get_user_db
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import rate_limited
from app.core.security import AuthenticatedUser
from app.intelligence.embeddings import FastEmbedEmbedder
from app.repositories import lectures as lecture_repo
from app.schemas.workspace import MediaAccess, QuestionAnswer, QuestionHistory, QuestionRequest, Workspace
from app.services import rag
from app.services.ingestion import BUCKET
from app.services.llm import LLMError, OpenAICompatibleProvider
from app.services.supabase_admin import ServiceSupabase
from app.services.supabase_rest import UserScopedSupabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lectures", tags=["workspace"])

NOT_FOUND = "Lecture not found."
CHAT_FIELDS = "id,question,outcome,answer,sources,latency_ms,created_at"


async def _owned_lecture(db: UserScopedSupabase, user: AuthenticatedUser, lecture_id: uuid.UUID) -> dict:
    lecture = await lecture_repo.get_lecture(db, user.id, lecture_id)
    if lecture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return lecture


@router.get("/{lecture_id}/workspace", response_model=Workspace)
async def get_workspace(
    lecture_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
):
    lecture = await _owned_lecture(db, user, lecture_id)
    by_lecture = {"lecture_id": f"eq.{lecture_id}"}
    transcript_rows, segments, chapters, intelligence, chunks = await asyncio.gather(
        db.select("transcripts", {"select": "language,model", **by_lecture}),
        db.select_all(
            "transcript_segments",
            {"select": "sequence,start_seconds,end_seconds,text", **by_lecture, "order": "sequence"},
        ),
        db.select("chapters", {"select": "*", **by_lecture, "order": "sequence"}),
        db.select(
            "lecture_intelligence",
            {
                "select": "summary,topics,key_concepts,definitions,keywords,important_points,examples,"
                "model,prompt_version,created_at",
                **by_lecture,
            },
        ),
        db.select_all("lecture_chunks", {"select": "sequence,start_seconds,end_seconds", **by_lecture, "order": "sequence"}),
    )
    transcript = None
    if transcript_rows:
        transcript = {
            **transcript_rows[0],
            # Cleaning marks removed segments (non-speech, repeats) with empty text; they aren't shown.
            "segments": [
                {"sequence": s["sequence"], "start": s["start_seconds"], "end": s["end_seconds"], "text": s["text"]}
                for s in segments
                if (s.get("text") or "").strip()
            ],
        }
    return {
        "lecture": lecture,
        "transcript": transcript,
        "chapters": chapters,
        "intelligence": intelligence[0] if intelligence else None,
        "chunks": [{"sequence": c["sequence"], "start": c["start_seconds"], "end": c["end_seconds"]} for c in chunks],
    }


@router.get("/{lecture_id}/media", response_model=MediaAccess)
async def get_media(
    lecture_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
    settings: Settings = Depends(get_settings),
):
    lecture = await _owned_lecture(db, user, lecture_id)
    rows = await db.select(
        "lecture_media",
        {"select": "kind,storage_path,mime_type,duration_seconds,probe", "lecture_id": f"eq.{lecture_id}"},
    )
    by_kind = {row["kind"]: row for row in rows}
    # A stored playback rendition exists only when there's no playable upload (source URLs).
    media = by_kind.get("original") or by_kind.get("playback")
    if media is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "media_unavailable", "This lecture has no playable media.")
    is_video = media["kind"] == "original" and lecture["source_type"] == "video" and (media.get("probe") or {}).get(
        "has_video", True
    )
    url = await db.signed_url(BUCKET, media["storage_path"], settings.media_url_ttl_seconds)
    return {
        "kind": "video" if is_video else "audio",
        "mime_type": media["mime_type"],
        "url": url,
        "expires_in": settings.media_url_ttl_seconds,
        "duration_seconds": media.get("duration_seconds") or lecture.get("duration_seconds"),
    }


@router.get("/{lecture_id}/questions", response_model=QuestionHistory)
async def list_questions(
    lecture_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
):
    await _owned_lecture(db, user, lecture_id)
    rows = await db.select(
        "chat_logs",
        {
            "select": CHAT_FIELDS,
            "lecture_id": f"eq.{lecture_id}",
            "user_id": f"eq.{user.id}",
            "order": "created_at.desc",
            "limit": str(limit),
        },
    )
    return {"items": rows}


def get_embedder(settings: Settings = Depends(get_settings)) -> FastEmbedEmbedder:
    return FastEmbedEmbedder(settings)


def get_qa_provider(request: Request, settings: Settings = Depends(get_settings)) -> OpenAICompatibleProvider | None:
    if not settings.llm_configured:
        return None
    # Interactive requests wait out at most a short provider rate limit.
    qa_settings = settings.model_copy(update={"llm_rate_limit_retries": settings.rag_rate_limit_retries})
    return OpenAICompatibleProvider(request.app.state.http, qa_settings)


def get_admin(request: Request, settings: Settings = Depends(get_settings)) -> ServiceSupabase:
    if not settings.ingestion_configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Questions are not configured.")
    return ServiceSupabase(request.app.state.http, settings)


@router.post(
    "/{lecture_id}/questions",
    response_model=QuestionAnswer,
    dependencies=[Depends(rate_limited("questions", "rate_limit_questions"))],
)
async def ask_question(
    lecture_id: uuid.UUID,
    body: QuestionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
    admin: ServiceSupabase = Depends(get_admin),
    embedder: FastEmbedEmbedder = Depends(get_embedder),
    provider: OpenAICompatibleProvider | None = Depends(get_qa_provider),
    settings: Settings = Depends(get_settings),
):
    lecture = await _owned_lecture(db, user, lecture_id)
    if lecture["status"] != "READY":
        raise AppError(
            status.HTTP_409_CONFLICT, "lecture_not_ready", "Questions can be asked once this lecture has finished processing."
        )
    indexed = await db.select("lecture_chunks", {"select": "embedding_model", "lecture_id": f"eq.{lecture_id}", "limit": "1"})
    if not indexed or indexed[0]["embedding_model"] != embedder.name:
        # Never compare a query vector with vectors from a different model or dimension.
        raise AppError(
            status.HTTP_409_CONFLICT,
            "index_incompatible",
            "This lecture's search index was built with a different embedding model and must be re-processed.",
        )

    async def retrieve(vector: str, count: int) -> list[dict]:
        # As the user: the function is SECURITY INVOKER, so RLS limits it to their own lecture.
        return await db.rpc(
            "match_lecture_chunks", {"p_lecture_id": str(lecture_id), "p_query_embedding": vector, "p_match_count": count}
        )

    try:
        result = await rag.answer_question(
            question=body.question, lecture=lecture, retrieve=retrieve, embedder=embedder, provider=provider, settings=settings
        )
    except LLMError as error:
        logger.warning(
            "qa_failed lecture_id=%s error_code=%s status=%s", lecture_id, error.code, (error.details or {}).get("status", "-")
        )
        if error.code == "llm_not_configured":
            raise AppError(status.HTTP_503_SERVICE_UNAVAILABLE, error.code, "Answering questions isn't configured on the server.") from None
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "answer_unavailable",
            "An answer couldn't be generated right now. Please try again in a moment.",
        ) from None

    logger.info(
        "qa_answered lecture_id=%s outcome=%s decision=%s retrieval_ms=%s llm_ms=%s latency_ms=%s",
        lecture_id, result.outcome, result.retrieval.get("decision"), result.retrieval_ms, result.llm_ms, result.latency_ms,
    )
    row = await admin.insert(
        "chat_logs",
        {
            "lecture_id": str(lecture_id),
            "user_id": str(user.id),
            "question": body.question,
            "outcome": result.outcome,
            "answer": result.answer,
            "sources": result.sources,
            "retrieval": result.retrieval,
            "embedding_model": embedder.name,
            "llm_provider": result.llm_provider,
            "llm_model": result.llm_model,
            "prompt_version": rag.PROMPT_VERSION,
            "retrieval_ms": result.retrieval_ms,
            "llm_ms": result.llm_ms,
            "latency_ms": result.latency_ms,
        },
    )
    return {key: row[key] for key in CHAT_FIELDS.split(",")}


@router.delete("/{lecture_id}/questions", status_code=status.HTTP_204_NO_CONTENT)
async def clear_questions(
    lecture_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
    admin: ServiceSupabase = Depends(get_admin),
):
    """Delete all of the caller's questions about one of their lectures."""
    await _owned_lecture(db, user, lecture_id)
    await admin.delete("chat_logs", {"lecture_id": f"eq.{lecture_id}", "user_id": f"eq.{user.id}"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
