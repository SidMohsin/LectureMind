"""Sentence-aware chunking over timestamped transcript segments.

Chunks are built from whole transcript segments, so every chunk's start/end time
is exact (the first segment's start and the last segment's end). A chunk closes
at the first sentence end after reaching the minimum size, or at the maximum
size if no sentence end comes. Consecutive chunks share a small overlap of
trailing segments so an idea split across a boundary is retrievable from both.

Deterministic: the same segments and configuration always give the same chunks.
"""

import math
import re
from dataclasses import dataclass

SENTENCE_END = re.compile(r"[.!?][\"')\]]*$")
# Tokens per word for English sub-word tokenizers (conservative estimate).
TOKENS_PER_WORD = 1.3


@dataclass(frozen=True)
class Segment:
    sequence: int
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Chunk:
    sequence: int
    text: str
    start: float
    end: float
    first_segment: int
    last_segment: int
    token_estimate: int


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text.split()) * TOKENS_PER_WORD))


def _make(sequence: int, segments: list[Segment]) -> Chunk:
    text = " ".join(segment.text for segment in segments)
    return Chunk(
        sequence=sequence,
        text=text,
        start=segments[0].start,
        end=segments[-1].end,
        first_segment=segments[0].sequence,
        last_segment=segments[-1].sequence,
        token_estimate=estimate_tokens(text),
    )


def _overlap_tail(segments: list[Segment], overlap_tokens: int) -> list[Segment]:
    tail: list[Segment] = []
    used = 0
    for segment in reversed(segments):
        cost = estimate_tokens(segment.text)
        if used + cost > overlap_tokens:
            break
        tail.insert(0, segment)
        used += cost
    return tail


def build_chunks(segments: list[Segment], *, min_tokens: int, max_tokens: int, overlap_tokens: int) -> list[Chunk]:
    if not 0 <= overlap_tokens < min_tokens <= max_tokens:
        raise ValueError("Expected 0 <= overlap < min <= max tokens.")
    segments = [segment for segment in segments if segment.text.strip()]
    groups: list[list[Segment]] = []
    current: list[Segment] = []
    fresh = 0  # tokens in `current` that aren't overlap from the previous chunk

    for segment in segments:
        cost = estimate_tokens(segment.text)
        # Close before this segment if it would push us past the maximum.
        if current and fresh >= min_tokens and fresh + cost > max_tokens:
            groups.append(current)
            current = _overlap_tail(current, overlap_tokens)
            fresh = 0
        current.append(segment)
        fresh += cost
        if fresh >= min_tokens and SENTENCE_END.search(segment.text.strip()):
            groups.append(current)
            current = _overlap_tail(current, overlap_tokens)
            fresh = 0

    if fresh > 0:
        # A short tail is merged into the previous chunk rather than left as a fragment.
        if groups and fresh < min_tokens / 2:
            previous = groups[-1]
            groups[-1] = previous + [segment for segment in current if segment not in previous]
        else:
            groups.append(current)

    return [_make(index, group) for index, group in enumerate(groups)]
