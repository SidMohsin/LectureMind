"""
Timestamp-aware overlapping chunking.

Cleaned transcript segments (each with its own start/end timestamp) are
merged into larger chunks of approximately CHUNK_SIZE_WORDS words, with an
overlap of CHUNK_OVERLAP_WORDS words between consecutive chunks. Each
resulting chunk records the start timestamp of its first contributing
segment and the end timestamp of its last contributing segment, so no
timestamp information is lost during chunking.
"""
from typing import List, Dict
from app.config import settings


def chunk_transcript(
    segments: List[Dict],
    chunk_size_words: int = None,
    overlap_words: int = None,
) -> List[Dict]:
    """
    Returns a list of chunks:
    [{"chunk_index": int, "start": float, "end": float, "text": str, "word_count": int}, ...]
    """
    chunk_size_words = chunk_size_words or settings.CHUNK_SIZE_WORDS
    overlap_words = overlap_words or settings.CHUNK_OVERLAP_WORDS

    if not segments:
        return []

    # Flatten segments into a list of (word, start_ts, end_ts) so timestamps
    # travel with each word and overlap can be computed precisely.
    word_stream = []
    for seg in segments:
        words = seg["text"].split(" ")
        if not words:
            continue
        n = len(words)
        seg_start, seg_end = seg["start"], seg["end"]
        for i, w in enumerate(words):
            # interpolate an approximate per-word timestamp within the segment
            frac_start = i / n
            frac_end = (i + 1) / n
            ts_start = seg_start + frac_start * (seg_end - seg_start)
            ts_end = seg_start + frac_end * (seg_end - seg_start)
            word_stream.append((w, ts_start, ts_end))

    chunks = []
    idx = 0
    step = max(chunk_size_words - overlap_words, 1)
    chunk_index = 0

    while idx < len(word_stream):
        window = word_stream[idx: idx + chunk_size_words]
        if not window:
            break
        text = " ".join(w for w, _, _ in window)
        start_ts = window[0][1]
        end_ts = window[-1][2]
        chunks.append({
            "chunk_index": chunk_index,
            "start": round(start_ts, 2),
            "end": round(end_ts, 2),
            "text": text,
            "word_count": len(window),
        })
        chunk_index += 1
        idx += step

    return chunks
