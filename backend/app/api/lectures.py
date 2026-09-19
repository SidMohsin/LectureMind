"""
REST API routes for LectureMind: upload, processing, status, transcript,
summary, keywords, chat and listing lectures.
"""
import os
import re
import json
import shutil
import mimetypes
import datetime as dt

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, SessionLocal
from app.models.lecture import Lecture, ChatLog
from app.schemas.lecture import (
    LectureUploadResponse, LectureStatusResponse, TranscriptResponse,
    SummaryResponse, KeywordsResponse, ChatRequest, ChatResponse,
    LectureListResponse, LectureListItem, SourceChunk,
    LectureDetailResponse, StatsResponse, ConfigResponse, DeleteResponse,
)
from app.utils.file_validation import validate_upload, safe_filename, FileValidationError
from app.services.pipeline import process_lecture
from app.services.rag import answer_question
from app.services.vector_store import VectorStoreError, delete_lecture_collection
from app.services.llm_provider import LLMError, LLMNotConfiguredError
from app.services.audio import AudioExtractionError
from app.services.whisper_service import TranscriptionError
from app.services.embeddings import EmbeddingError

router = APIRouter(prefix="/api", tags=["lectures"])


def _lecture_or_404(db: Session, lecture_id: str) -> Lecture:
    lecture = db.query(Lecture).filter(Lecture.lecture_id == lecture_id).first()
    if lecture is None:
        raise HTTPException(status_code=404, detail=f"Lecture '{lecture_id}' not found.")
    return lecture


@router.post("/lectures/upload", response_model=LectureUploadResponse)
async def upload_lecture(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        file_type = await validate_upload(file)
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    stored_name = safe_filename(file.filename)
    dest_path = os.path.join(settings.UPLOAD_DIR, stored_name)

    try:
        contents = await file.read()
        with open(dest_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    lecture = Lecture(
        original_filename=file.filename,
        stored_filename=stored_name,
        file_type=file_type,
        raw_media_path=dest_path,
        status="uploaded",
        status_message="File uploaded successfully. Ready for processing.",
        upload_time=dt.datetime.utcnow(),
    )
    db.add(lecture)
    db.commit()
    db.refresh(lecture)

    return LectureUploadResponse(
        lecture_id=lecture.lecture_id,
        original_filename=lecture.original_filename,
        file_type=lecture.file_type,
        status=lecture.status,
        message="Upload successful. Call /api/lectures/{lecture_id}/process to start the pipeline.",
    )


@router.post("/lectures/{lecture_id}/process", response_model=LectureStatusResponse)
def process_lecture_endpoint(lecture_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    lecture = _lecture_or_404(db, lecture_id)

    if lecture.status in ("extracting_audio", "transcribing", "cleaning", "chunking",
                           "embedding", "indexing", "summarizing", "extracting_keywords"):
        raise HTTPException(status_code=409, detail="Lecture is already being processed.")

    lecture.status = "queued"
    lecture.status_message = "Processing queued"
    lecture.error_message = None
    db.commit()

    background_tasks.add_task(process_lecture, lecture_id, SessionLocal)

    return LectureStatusResponse(
        lecture_id=lecture.lecture_id,
        status=lecture.status,
        status_message=lecture.status_message,
        num_chunks=lecture.num_chunks or 0,
    )


@router.get("/lectures/{lecture_id}/status", response_model=LectureStatusResponse)
def get_status(lecture_id: str, db: Session = Depends(get_db)):
    lecture = _lecture_or_404(db, lecture_id)
    return LectureStatusResponse(
        lecture_id=lecture.lecture_id,
        status=lecture.status,
        status_message=lecture.status_message,
        error_message=lecture.error_message,
        num_chunks=lecture.num_chunks or 0,
    )


@router.get("/lectures/{lecture_id}/transcript", response_model=TranscriptResponse)
def get_transcript(lecture_id: str, db: Session = Depends(get_db)):
    lecture = _lecture_or_404(db, lecture_id)
    if not lecture.transcript_path or not os.path.exists(lecture.transcript_path):
        raise HTTPException(status_code=404, detail="Transcript not available yet for this lecture.")
    with open(lecture.transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return TranscriptResponse(
        lecture_id=lecture_id,
        language=data.get("language"),
        segments=data.get("segments", []),
        full_text=data.get("full_text", ""),
    )


@router.get("/lectures/{lecture_id}/summary", response_model=SummaryResponse)
def get_summary(lecture_id: str, db: Session = Depends(get_db)):
    lecture = _lecture_or_404(db, lecture_id)
    if not lecture.summary_json:
        raise HTTPException(status_code=404, detail="Summary not available yet for this lecture.")
    data = json.loads(lecture.summary_json)
    return SummaryResponse(
        lecture_id=lecture_id,
        overview=data.get("overview", ""),
        main_concepts=data.get("main_concepts", []),
        important_points=data.get("important_points", []),
        key_takeaways=data.get("key_takeaways", []),
    )


@router.get("/lectures/{lecture_id}/keywords", response_model=KeywordsResponse)
def get_keywords(lecture_id: str, db: Session = Depends(get_db)):
    lecture = _lecture_or_404(db, lecture_id)
    if not lecture.keywords_json:
        raise HTTPException(status_code=404, detail="Keywords not available yet for this lecture.")
    return KeywordsResponse(lecture_id=lecture_id, keywords=json.loads(lecture.keywords_json))


@router.post("/lectures/{lecture_id}/chat", response_model=ChatResponse)
def chat_with_lecture(lecture_id: str, req: ChatRequest, db: Session = Depends(get_db)):
    lecture = _lecture_or_404(db, lecture_id)
    if lecture.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Lecture is not ready for chat yet (current status: '{lecture.status}')."
        )

    try:
        result = answer_question(lecture_id, req.question, req.top_k)
    except VectorStoreError as e:
        raise HTTPException(status_code=500, detail=f"Retrieval error: {e}")
    except LLMNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=f"LLM not configured: {e}")
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")
    except EmbeddingError as e:
        raise HTTPException(status_code=500, detail=f"Embedding error: {e}")

    log = ChatLog(
        lecture_id=lecture_id,
        question=req.question,
        answer=result["answer"],
        sources_json=json.dumps(result["sources"]),
        latency_ms=result["latency_ms"],
    )
    db.add(log)
    db.commit()

    sources = [SourceChunk(**s) for s in result["sources"]]
    return ChatResponse(
        lecture_id=lecture_id,
        question=req.question,
        answer=result["answer"],
        grounded=result["grounded"],
        sources=sources,
        latency_ms=result["latency_ms"],
    )


@router.get("/lectures", response_model=LectureListResponse)
def list_lectures(db: Session = Depends(get_db)):
    lectures = db.query(Lecture).order_by(Lecture.upload_time.desc()).all()
    items = [
        LectureListItem(
            lecture_id=l.lecture_id,
            original_filename=l.original_filename,
            file_type=l.file_type,
            status=l.status,
            upload_time=l.upload_time.isoformat() if l.upload_time else "",
            duration_seconds=l.duration_seconds,
            num_chunks=l.num_chunks or 0,
        )
        for l in lectures
    ]
    return LectureListResponse(lectures=items)


@router.get("/lectures/{lecture_id}", response_model=LectureDetailResponse)
def get_lecture_detail(lecture_id: str, db: Session = Depends(get_db)):
    lecture = _lecture_or_404(db, lecture_id)
    return LectureDetailResponse(
        lecture_id=lecture.lecture_id,
        original_filename=lecture.original_filename,
        file_type=lecture.file_type,
        status=lecture.status,
        status_message=lecture.status_message,
        error_message=lecture.error_message,
        upload_time=lecture.upload_time.isoformat() if lecture.upload_time else "",
        duration_seconds=lecture.duration_seconds,
        num_chunks=lecture.num_chunks or 0,
        has_media=bool(lecture.raw_media_path and os.path.exists(lecture.raw_media_path)),
        processing_started_at=lecture.processing_started_at.isoformat() if lecture.processing_started_at else None,
        processing_completed_at=lecture.processing_completed_at.isoformat() if lecture.processing_completed_at else None,
    )


@router.delete("/lectures/{lecture_id}", response_model=DeleteResponse)
def delete_lecture(lecture_id: str, db: Session = Depends(get_db)):
    lecture = _lecture_or_404(db, lecture_id)

    # Remove files on disk (best-effort — a missing file should not block deletion).
    for path in (lecture.raw_media_path, lecture.audio_path, lecture.transcript_path):
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    summary_path = os.path.join(settings.SUMMARY_DIR, f"{lecture_id}_summary.json")
    if os.path.exists(summary_path):
        try:
            os.remove(summary_path)
        except OSError:
            pass

    # Remove the ChromaDB collection so no orphaned vectors remain.
    delete_lecture_collection(lecture_id)

    # Remove chat history and the lecture row itself.
    db.query(ChatLog).filter(ChatLog.lecture_id == lecture_id).delete()
    db.delete(lecture)
    db.commit()

    return DeleteResponse(lecture_id=lecture_id, deleted=True, message="Lecture deleted successfully.")


@router.get("/lectures/{lecture_id}/media")
def get_lecture_media(lecture_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Streams the original uploaded media file with HTTP Range support, so the
    frontend's <video>/<audio> element can play it and seek within it.
    """
    lecture = _lecture_or_404(db, lecture_id)
    path = lecture.raw_media_path

    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Media file not available for this lecture.")

    file_size = os.path.getsize(path)
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    range_header = request.headers.get("range")

    def iter_range(start: int, end: int, chunk_size: int = 1024 * 1024):
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                data = f.read(read_size)
                if not data:
                    break
                remaining -= len(data)
                yield data

    if range_header:
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not match:
            raise HTTPException(status_code=416, detail="Invalid Range header.")
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else file_size - 1
        end = min(end, file_size - 1)

        if start > end or start >= file_size:
            raise HTTPException(status_code=416, detail="Requested range not satisfiable.")

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
        }
        return StreamingResponse(
            iter_range(start, end),
            status_code=206,
            media_type=content_type,
            headers=headers,
        )

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(file_size)}
    return StreamingResponse(iter_range(0, file_size - 1), media_type=content_type, headers=headers)


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    lectures = db.query(Lecture).all()
    total_questions = db.query(ChatLog).count()

    completed = sum(1 for l in lectures if l.status == "completed")
    failed = sum(1 for l in lectures if l.status == "failed")
    processing_statuses = {
        "uploaded", "queued", "extracting_audio", "transcribing", "cleaning",
        "chunking", "embedding", "indexing", "summarizing", "extracting_keywords",
    }
    processing = sum(1 for l in lectures if l.status in processing_statuses)
    total_duration = sum(l.duration_seconds or 0.0 for l in lectures)

    return StatsResponse(
        total_lectures=len(lectures),
        completed_lectures=completed,
        processing_lectures=processing,
        failed_lectures=failed,
        total_duration_seconds=total_duration,
        total_questions_asked=total_questions,
    )


@router.get("/config", response_model=ConfigResponse)
def get_config():
    provider = settings.LLM_PROVIDER.lower()
    if provider == "ollama":
        model = settings.OLLAMA_MODEL
    elif provider == "openai":
        model = settings.OPENAI_MODEL
    elif provider == "groq":
        model = settings.GROQ_MODEL
    else:
        model = "unknown"

    return ConfigResponse(
        llm_provider=settings.LLM_PROVIDER,
        llm_model=model,
        embedding_model=settings.EMBEDDING_MODEL,
        whisper_model_size=settings.WHISPER_MODEL_SIZE,
        whisper_device=settings.WHISPER_DEVICE,
        top_k=settings.TOP_K,
        chunk_size_words=settings.CHUNK_SIZE_WORDS,
        chunk_overlap_words=settings.CHUNK_OVERLAP_WORDS,
    )
