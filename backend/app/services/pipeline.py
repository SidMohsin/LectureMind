"""
End-to-end lecture processing pipeline orchestrator.

Runs as a FastAPI BackgroundTask so the HTTP request returns immediately
and the frontend can poll /status while processing continues. Updates the
Lecture row's `status` field at each stage so the frontend can display
progress (Extracting audio -> Transcribing -> Cleaning -> Chunking ->
Embedding -> Indexing -> Summarizing -> Extracting keywords -> Completed).
"""
import os
import json
import traceback
import datetime as dt

from sqlalchemy.orm import Session
from app.config import settings
from app.models.lecture import Lecture
from app.services import audio as audio_service
from app.services import whisper_service
from app.services import transcript as transcript_service
from app.services import chunking as chunking_service
from app.services import embeddings as embeddings_service
from app.services import vector_store
from app.services import summarizer
from app.services import keywords as keywords_service


def _set_status(db: Session, lecture: Lecture, status: str, message: str = ""):
    lecture.status = status
    lecture.status_message = message
    db.add(lecture)
    db.commit()
    db.refresh(lecture)


def process_lecture(lecture_id: str, db_factory):
    """
    db_factory: a zero-arg callable returning a new SQLAlchemy Session
    (BackgroundTasks run outside the request's DB session lifecycle, so we
    open a fresh session here).
    """
    db: Session = db_factory()
    try:
        lecture = db.query(Lecture).filter(Lecture.lecture_id == lecture_id).first()
        if lecture is None:
            return

        lecture.processing_started_at = dt.datetime.utcnow()
        db.commit()

        input_path = lecture.raw_media_path

        # --- Stage 1: Extract / standardise audio ---
        _set_status(db, lecture, "extracting_audio", "Extracting audio track with FFmpeg")
        audio_out_path = os.path.join(settings.AUDIO_DIR, f"{lecture_id}.wav")
        audio_service.extract_audio(input_path, audio_out_path)
        duration = audio_service.get_media_duration_seconds(audio_out_path)
        lecture.audio_path = audio_out_path
        lecture.duration_seconds = duration
        db.commit()

        # --- Stage 2: Whisper transcription ---
        _set_status(db, lecture, "transcribing", "Transcribing audio with Whisper (this can take a while)")
        result = whisper_service.transcribe_audio(audio_out_path)
        raw_segments = result["segments"]

        # --- Stage 3: Transcript cleaning ---
        _set_status(db, lecture, "cleaning", "Cleaning transcript text")
        cleaned_segments = transcript_service.clean_transcript(raw_segments)
        full_text = transcript_service.segments_to_plain_text(cleaned_segments)

        transcript_path = os.path.join(settings.TRANSCRIPT_DIR, f"{lecture_id}.json")
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump({
                "language": result.get("language"),
                "segments": cleaned_segments,
                "full_text": full_text,
            }, f, ensure_ascii=False, indent=2)
        lecture.transcript_path = transcript_path
        db.commit()

        # --- Stage 4: Timestamp-aware chunking ---
        _set_status(db, lecture, "chunking", "Splitting transcript into overlapping chunks")
        chunks = chunking_service.chunk_transcript(cleaned_segments)
        if not chunks:
            raise RuntimeError("Chunking produced no chunks from the transcript.")

        # --- Stage 5: Embeddings ---
        _set_status(db, lecture, "embedding", f"Generating embeddings for {len(chunks)} chunks")
        chunk_texts = [c["text"] for c in chunks]
        vectors = embeddings_service.embed_texts(chunk_texts)

        # --- Stage 6: Index in ChromaDB ---
        _set_status(db, lecture, "indexing", "Indexing chunks in ChromaDB")
        num_indexed = vector_store.index_chunks(lecture_id, chunks, vectors)
        lecture.num_chunks = num_indexed
        db.commit()

        # --- Stage 7: Summarization ---
        _set_status(db, lecture, "summarizing", "Generating lecture summary")
        try:
            summary = summarizer.generate_summary(full_text)
        except Exception as e:
            summary = {
                "overview": "Summary generation failed.",
                "main_concepts": [],
                "important_points": [],
                "key_takeaways": [],
            }
            lecture.error_message = f"Summary generation warning: {e}"
        summary_path = os.path.join(settings.SUMMARY_DIR, f"{lecture_id}_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        lecture.summary_json = json.dumps(summary, ensure_ascii=False)
        db.commit()

        # --- Stage 8: Keyword extraction ---
        _set_status(db, lecture, "extracting_keywords", "Extracting important keywords")
        try:
            kws = keywords_service.extract_keywords(full_text)
        except Exception as e:
            kws = []
            lecture.error_message = ((lecture.error_message or "") + f" | Keyword extraction warning: {e}").strip(" |")
        lecture.keywords_json = json.dumps(kws, ensure_ascii=False)
        db.commit()

        # --- Done ---
        lecture.processing_completed_at = dt.datetime.utcnow()
        _set_status(db, lecture, "completed", "Processing completed successfully")

    except Exception as e:
        tb = traceback.format_exc()
        try:
            lecture = db.query(Lecture).filter(Lecture.lecture_id == lecture_id).first()
            if lecture:
                lecture.status = "failed"
                lecture.status_message = "Processing failed"
                lecture.error_message = f"{str(e)}"
                db.commit()
        finally:
            # Full traceback is kept server-side in logs only; never sent to the client.
            print(f"[LectureMind] Processing failed for lecture {lecture_id}:\n{tb}")
    finally:
        db.close()
