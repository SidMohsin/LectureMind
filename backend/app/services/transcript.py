"""
Transcript cleaning service.

Cleans raw Whisper segment text while preserving timestamps and technical
terms: normalises whitespace, fixes punctuation spacing, and removes
common filler/disfluency tokens without altering meaning.
"""
import re
from typing import List, Dict

DISFLUENCIES = {
    "um", "uh", "umm", "uhh", "erm", "hmm", "you know", "i mean", "like,",
}


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_punctuation(text: str) -> str:
    # collapse repeated punctuation, fix spacing before punctuation
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,.!?;:]){2,}", r"\1", text)
    # ensure a single space after sentence punctuation
    text = re.sub(r"([.!?])(?=[A-Za-z])", r"\1 ", text)
    return text


def _remove_disfluencies(text: str) -> str:
    words = text.split(" ")
    cleaned = []
    for w in words:
        w_lower = w.lower().strip(",.")
        if w_lower in DISFLUENCIES:
            continue
        cleaned.append(w)
    return " ".join(cleaned)


def clean_segment_text(text: str) -> str:
    text = _normalize_whitespace(text)
    text = _remove_disfluencies(text)
    text = _normalize_punctuation(text)
    text = _normalize_whitespace(text)
    return text


def clean_transcript(segments: List[Dict]) -> List[Dict]:
    """
    Clean each segment's text in place (returns new list). Timestamps are
    never modified — only the `text` field is cleaned. Segments that become
    empty after cleaning are dropped, but this is rare since disfluency
    removal only strips filler tokens.
    """
    cleaned = []
    for seg in segments:
        new_text = clean_segment_text(seg["text"])
        if new_text:
            cleaned.append({"start": seg["start"], "end": seg["end"], "text": new_text})
    return cleaned


def segments_to_plain_text(segments: List[Dict]) -> str:
    return " ".join(s["text"] for s in segments)
