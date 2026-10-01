"""Conservative, deterministic transcript cleaning.

Cleaning works segment by segment, so every cleaned segment keeps the exact
start/end time of the segment it came from. It only normalizes formatting and
removes well-known speech-recognition artifacts; it never rewrites, reorders or
adds words. The raw text is stored alongside the cleaned text.
"""

import re
import unicodedata
from dataclasses import dataclass, field

# Whisper's own heuristic for "this segment is probably not speech".
NO_SPEECH_PROB_THRESHOLD = 0.8
LOW_LOGPROB_THRESHOLD = -1.0
SENTENCE_END = re.compile(r"[.!?][\"')\]]*$")


@dataclass(frozen=True)
class RawSegment:
    sequence: int
    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


@dataclass
class CleaningStats:
    segments: int = 0
    removed_duplicate_segments: int = 0
    removed_non_speech_segments: int = 0
    removed_empty_segments: int = 0
    collapsed_repetitions: int = 0
    changed_segments: int = 0
    notes: list[str] = field(default_factory=list)

    def as_record(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if key != "notes"}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?%)\]])", r"\1", text)  # "word ," -> "word,"
    text = re.sub(r"([(\[])\s+", r"\1", text)  # "( word" -> "(word"
    return text


def _collapse_repeated_sentences(text: str) -> tuple[str, int]:
    """Whisper sometimes loops, e.g. "Thank you. Thank you. Thank you." -> keep one.

    Only exact repeats of a whole sentence, three or more times in a row, are
    collapsed; ordinary emphasis ("very, very") is left alone.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    runs: list[list[str]] = []
    for sentence in sentences:
        if runs and sentence.lower() == runs[-1][0].lower():
            runs[-1].append(sentence)
        else:
            runs.append([sentence])
    kept: list[str] = []
    collapsed = 0
    for run in runs:
        if len(run) >= 3:
            kept.append(run[0])
            collapsed += len(run) - 1
        else:
            kept.extend(run)
    return " ".join(kept), collapsed


def _normalized_key(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def clean_segments(segments: list[RawSegment]) -> tuple[list[str], CleaningStats]:
    """Returns one cleaned text per input segment ("" = removed) and statistics."""
    stats = CleaningStats(segments=len(segments))
    cleaned: list[str] = []
    previous_key = None
    sentence_open = False  # the previous kept segment ended mid-sentence

    for segment in segments:
        text = _normalize(segment.text)

        if (
            segment.no_speech_prob is not None
            and segment.avg_logprob is not None
            and segment.no_speech_prob >= NO_SPEECH_PROB_THRESHOLD
            and segment.avg_logprob <= LOW_LOGPROB_THRESHOLD
        ):
            stats.removed_non_speech_segments += 1
            cleaned.append("")
            continue

        text, collapsed = _collapse_repeated_sentences(text)
        stats.collapsed_repetitions += collapsed

        key = _normalized_key(text)
        if not key:
            stats.removed_empty_segments += 1
            cleaned.append("")
            continue
        if key == previous_key:  # the same segment text emitted twice in a row
            stats.removed_duplicate_segments += 1
            cleaned.append("")
            continue

        if not sentence_open and text[0].islower():
            text = text[0].upper() + text[1:]

        if text != segment.text.strip():
            stats.changed_segments += 1
        cleaned.append(text)
        previous_key = key
        sentence_open = not SENTENCE_END.search(text)

    return cleaned, stats
