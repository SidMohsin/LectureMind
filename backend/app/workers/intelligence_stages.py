"""Phase 5 stages: TRANSCRIBING -> CLEANING -> CHUNKING -> EMBEDDING -> INDEXING -> GENERATING_INTELLIGENCE.

Each stage reads its input from the database (or, for transcription, the audio
prepared in the job workspace) and replaces its own output for the lecture, so
re-running a stage after a crash or retry never duplicates rows. Each returns
measured details (model, configuration, counts, timings) that are stored on the
stage run for later evaluation.
"""

import asyncio
import statistics
import time

import httpx

from app.intelligence.chunking import Segment, build_chunks
from app.intelligence.cleaning import RawSegment, clean_segments
from app.intelligence.embeddings import FastEmbedEmbedder, to_pgvector
from app.intelligence.generation import PROMPT_VERSION, ChunkRef, generate
from app.intelligence.transcription import FasterWhisperTranscriber, TranscriptionCancelled, TranscriptionProgress
from app.services.llm import LLMError, OpenAICompatibleProvider
from app.workers.context import JobContext
from app.workers.lifecycle import ProcessingError
from app.workers.stages import prepare_audio

PROGRESS_INTERVAL_SECONDS = 10
SEGMENT_FIELDS = "sequence,start_seconds,end_seconds,raw_text,text,avg_logprob,no_speech_prob"
CHUNK_FIELDS = "id,lecture_id,sequence,text,start_seconds,end_seconds,first_segment,last_segment,token_estimate"


def _clock(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _lecture_filter(ctx: JobContext) -> dict:
    return {"lecture_id": f"eq.{ctx.lecture['id']}"}


# --- TRANSCRIBING ----------------------------------------------------------------------------


async def transcribe(ctx: JobContext) -> dict:
    audio = await prepare_audio(ctx)
    transcriber = FasterWhisperTranscriber(ctx.settings)
    progress = TranscriptionProgress(total_seconds=audio.duration_seconds)

    started = time.monotonic()
    work = asyncio.create_task(asyncio.to_thread(transcriber.transcribe, audio.path, progress))
    try:
        while True:
            done, _ = await asyncio.wait({work}, timeout=PROGRESS_INTERVAL_SECONDS)
            if done:
                break
            if progress.processed_seconds:
                await ctx.report(
                    f"Transcribing: {_clock(progress.processed_seconds)} of {_clock(progress.total_seconds)} of audio"
                )
            else:
                await ctx.report("Loading the speech recognition model")
        transcript = work.result()
    except TranscriptionCancelled:
        raise
    finally:
        if not work.done():
            progress.cancelled = True  # stop the thread at its next segment
    elapsed = time.monotonic() - started

    if not transcript.segments:
        raise ProcessingError("no_speech_detected", "No speech could be recognised in this lecture's audio.")

    rows = [
        {
            "lecture_id": ctx.lecture["id"],
            "sequence": index,
            "start_seconds": segment.start,
            "end_seconds": segment.end,
            "raw_text": segment.text.strip(),
            "text": None,
            "avg_logprob": segment.avg_logprob,
            "no_speech_prob": segment.no_speech_prob,
        }
        for index, segment in enumerate(transcript.segments)
    ]
    await ctx.ensure_active()
    await ctx.admin.delete("transcript_segments", _lecture_filter(ctx))
    await ctx.admin.insert_many("transcript_segments", rows)
    await ctx.admin.insert(
        "transcripts",
        {
            "lecture_id": ctx.lecture["id"],
            "language": transcript.language,
            "language_probability": transcript.language_probability,
            "audio_duration_seconds": round(transcript.duration_seconds, 3),
            "segment_count": len(rows),
            "model": transcript.model,
            "model_config": transcript.model_config,
        },
        on_conflict="lecture_id",
    )
    return {
        "model": transcript.model,
        "model_config": transcript.model_config,
        "language": transcript.language,
        "language_probability": transcript.language_probability,
        "audio_seconds": transcript.duration_seconds,
        "segments": len(rows),
        "transcribe_seconds": round(elapsed, 1),
        # Processing time per second of audio: the standard ASR speed measure.
        "real_time_factor": round(elapsed / transcript.duration_seconds, 3) if transcript.duration_seconds else None,
    }


# --- CLEANING --------------------------------------------------------------------------------


async def clean(ctx: JobContext) -> dict:
    rows = await ctx.admin.select_all(
        "transcript_segments", {"select": SEGMENT_FIELDS, **_lecture_filter(ctx), "order": "sequence.asc"}
    )
    if not rows:
        raise ProcessingError("transcript_missing", "The transcript for this lecture is missing.", retryable=False)
    segments = [
        RawSegment(
            sequence=row["sequence"],
            start=float(row["start_seconds"]),
            end=float(row["end_seconds"]),
            text=row["raw_text"],
            avg_logprob=row["avg_logprob"],
            no_speech_prob=row["no_speech_prob"],
        )
        for row in rows
    ]
    cleaned, stats = clean_segments(segments)
    updated = [{**row, "lecture_id": ctx.lecture["id"], "text": text} for row, text in zip(rows, cleaned)]
    await ctx.ensure_active()
    await ctx.admin.insert_many("transcript_segments", updated, on_conflict="lecture_id,sequence")
    return {"cleaning": stats.as_record(), "kept_segments": sum(1 for text in cleaned if text)}


# --- CHUNKING --------------------------------------------------------------------------------


async def chunk(ctx: JobContext) -> dict:
    settings = ctx.settings
    rows = await ctx.admin.select_all(
        "transcript_segments", {"select": SEGMENT_FIELDS, **_lecture_filter(ctx), "order": "sequence.asc"}
    )
    segments = [
        Segment(sequence=row["sequence"], start=float(row["start_seconds"]), end=float(row["end_seconds"]), text=row["text"])
        for row in rows
        if row["text"]
    ]
    config = {
        "min_tokens": settings.chunk_min_tokens,
        "max_tokens": settings.chunk_max_tokens,
        "overlap_tokens": settings.chunk_overlap_tokens,
    }
    chunks = build_chunks(segments, **config)
    if not chunks:
        raise ProcessingError("transcript_empty", "The transcript has no usable text after cleaning.")

    await ctx.ensure_active()
    await ctx.admin.delete("lecture_chunks", _lecture_filter(ctx))
    await ctx.admin.insert_many(
        "lecture_chunks",
        [
            {
                "lecture_id": ctx.lecture["id"],
                "sequence": c.sequence,
                "text": c.text,
                "start_seconds": c.start,
                "end_seconds": c.end,
                "first_segment": c.first_segment,
                "last_segment": c.last_segment,
                "token_estimate": c.token_estimate,
            }
            for c in chunks
        ],
    )
    sizes = [c.token_estimate for c in chunks]
    return {
        "config": config,
        "chunks": len(chunks),
        "tokens_min": min(sizes),
        "tokens_median": statistics.median(sizes),
        "tokens_max": max(sizes),
    }


# --- EMBEDDING -------------------------------------------------------------------------------


async def embed(ctx: JobContext) -> dict:
    embedder = FastEmbedEmbedder(ctx.settings)
    rows = await ctx.admin.select_all("lecture_chunks", {"select": CHUNK_FIELDS, **_lecture_filter(ctx), "order": "sequence.asc"})
    if not rows:
        raise ProcessingError("chunks_missing", "The lecture's transcript chunks are missing.")

    started = time.monotonic()
    vectors = await asyncio.to_thread(embedder.embed_passages, [row["text"] for row in rows])
    elapsed = time.monotonic() - started

    await ctx.ensure_active()
    await ctx.admin.insert_many(
        "lecture_chunks",
        [{**row, "embedding": to_pgvector(vector), "embedding_model": embedder.name} for row, vector in zip(rows, vectors)],
        on_conflict="id",
    )
    return {"model": embedder.name, "dimension": embedder.dimension, "chunks": len(rows), "embed_seconds": round(elapsed, 2)}


# --- INDEXING --------------------------------------------------------------------------------


async def index(ctx: JobContext) -> dict:
    """pgvector maintains the HNSW index on write; this stage verifies the result is searchable."""
    settings = ctx.settings
    rows = await ctx.admin.select_all(
        "lecture_chunks", {"select": "id,sequence,embedding,embedding_model", **_lecture_filter(ctx), "order": "sequence.asc"}
    )
    missing = [row["sequence"] for row in rows if row["embedding"] is None]
    wrong_model = [row["sequence"] for row in rows if row["embedding"] and row["embedding_model"] != settings.embedding_model]
    if not rows or missing or wrong_model:
        raise ProcessingError(
            "index_incomplete",
            "Some lecture sections weren't embedded correctly.",
            retryable=True,
            details={"missing": missing[:20], "wrong_model": wrong_model[:20]},
        )

    # Self-retrieval check: each probed chunk's own vector must retrieve that chunk first.
    probes = sorted({rows[0]["sequence"], rows[len(rows) // 2]["sequence"], rows[-1]["sequence"]})
    similarities = []
    for probe in probes:
        row = next(r for r in rows if r["sequence"] == probe)
        matches = await ctx.admin.rpc(
            "match_lecture_chunks",
            {"p_lecture_id": ctx.lecture["id"], "p_query_embedding": row["embedding"], "p_match_count": 3},
        )
        if not matches or matches[0]["chunk_id"] != row["id"]:
            raise ProcessingError(
                "index_verification_failed", "The lecture's search index didn't verify.", retryable=True,
                details={"probe": probe},
            )
        similarities.append(round(matches[0]["similarity"], 4))
    return {"indexed_chunks": len(rows), "dimension": settings.embedding_dimension, "self_retrieval_probes": probes,
            "self_similarity": similarities}


# --- GENERATING_INTELLIGENCE -----------------------------------------------------------------


async def generate_intelligence(ctx: JobContext) -> dict:
    settings = ctx.settings
    if not settings.llm_configured:
        raise ProcessingError(
            "llm_not_configured",
            "Lecture notes can't be generated because no language model is configured on the server.",
            retryable=True,
        )
    rows = await ctx.admin.select_all(
        "lecture_chunks", {"select": "sequence,text,start_seconds,end_seconds", **_lecture_filter(ctx), "order": "sequence.asc"}
    )
    chunks = [ChunkRef(r["sequence"], float(r["start_seconds"]), float(r["end_seconds"]), r["text"]) for r in rows]
    if not chunks:
        raise ProcessingError("chunks_missing", "The lecture's transcript chunks are missing.")

    await ctx.report("Generating summary, chapters and key concepts")
    started = time.monotonic()
    async with httpx.AsyncClient() as http:
        provider = OpenAICompatibleProvider(http, settings)
        try:
            result, report = await generate(provider, chunks, settings.llm_window_tokens, settings.llm_max_output_tokens)
        except LLMError as exc:
            raise ProcessingError(exc.code, exc.message, retryable=exc.retryable, details=exc.details) from None
    elapsed = time.monotonic() - started

    generation = {
        "windows": report.windows,
        "reduce_levels": report.reduce_levels,
        "max_output_tokens": settings.llm_max_output_tokens,
        "rate_limited_seconds": round(provider.usage.rate_limited_seconds, 1),
        "dropped_ungrounded_items": report.dropped_items,
        "temperature": settings.llm_temperature,
        "llm_calls": provider.usage.calls,
        "prompt_tokens": provider.usage.prompt_tokens,
        "completion_tokens": provider.usage.completion_tokens,
        "finish_reasons": [call.get("finish_reason") for call in provider.usage.per_call],
        "llm_seconds": round(elapsed, 1),
    }
    await ctx.ensure_active()
    await ctx.admin.delete("chapters", _lecture_filter(ctx))
    await ctx.admin.insert_many(
        "chapters", [{**chapter, "lecture_id": ctx.lecture["id"]} for chapter in result["chapters"]]
    )
    await ctx.admin.insert(
        "lecture_intelligence",
        {
            "lecture_id": ctx.lecture["id"],
            "summary": result["summary"],
            "topics": result["topics"],
            "key_concepts": result["key_concepts"],
            "definitions": result["definitions"],
            "keywords": result["keywords"],
            "important_points": result["important_points"],
            "examples": result["examples"],
            "provider": provider.name,
            "model": provider.model,
            "prompt_version": PROMPT_VERSION,
            "generation": generation,
        },
        on_conflict="lecture_id",
    )
    return {
        "provider": provider.name,
        "model": provider.model,
        "prompt_version": PROMPT_VERSION,
        **generation,
        "counts": {key: len(value) for key, value in result.items() if isinstance(value, list)},
    }
