"""Retrieval metrics against gold supporting spans.

Definitions (fixed; changing them requires a new METRICS_VERSION):

* A retrieved chunk [s, e] is *relevant* to a question when it overlaps any gold span
  [gs, ge] widened by the tolerance: max(s, gs - tol) < min(e, ge + tol).
* Hit@K: 1 if any of the top-K retrieved chunks is relevant, else 0.
* Recall@K: fraction of the question's gold spans overlapped by at least one top-K chunk.
  (With one gold span per question, Recall@K equals Hit@K.)
* MRR: mean over questions of 1/rank of the first relevant chunk (0 when none is
  retrieved in the ranked list given).
* Timestamp hit@K: 1 if the *start time* of any top-K chunk (the position the player
  seeks to when the source is clicked) lies within [gs - tol, ge + tol] of a gold span.
  This scores the citation's seek point, which overlap alone doesn't.

Defaults use a 30-second tolerance, the tolerance used for timestamp hit in the
"Cite or Decline" EduVidQA evaluation; it is a parameter so it can be reported or varied.

Only questions with gold spans (answerable questions) are scored. Similarity scores are
never used as evidence of relevance.
"""

from dataclasses import dataclass
from statistics import fmean

METRICS_VERSION = "retrieval-metrics/v1"
DEFAULT_TOLERANCE_SECONDS = 30.0


@dataclass(frozen=True)
class Span:
    start: float
    end: float


@dataclass(frozen=True)
class Retrieved:
    start: float
    end: float


def _overlaps(chunk: Retrieved, span: Span, tolerance: float) -> bool:
    return max(chunk.start, span.start - tolerance) < min(chunk.end, span.end + tolerance)


def is_relevant(chunk: Retrieved, spans: list[Span], tolerance: float = DEFAULT_TOLERANCE_SECONDS) -> bool:
    return any(_overlaps(chunk, span, tolerance) for span in spans)


def hit_at_k(ranked: list[Retrieved], spans: list[Span], k: int, tolerance: float = DEFAULT_TOLERANCE_SECONDS) -> float:
    _require(spans, k)
    return 1.0 if any(is_relevant(chunk, spans, tolerance) for chunk in ranked[:k]) else 0.0


def recall_at_k(ranked: list[Retrieved], spans: list[Span], k: int, tolerance: float = DEFAULT_TOLERANCE_SECONDS) -> float:
    _require(spans, k)
    covered = sum(1 for span in spans if any(_overlaps(chunk, span, tolerance) for chunk in ranked[:k]))
    return covered / len(spans)


def reciprocal_rank(ranked: list[Retrieved], spans: list[Span], tolerance: float = DEFAULT_TOLERANCE_SECONDS) -> float:
    _require(spans, 1)
    for rank, chunk in enumerate(ranked, start=1):
        if is_relevant(chunk, spans, tolerance):
            return 1.0 / rank
    return 0.0


def timestamp_hit_at_k(ranked: list[Retrieved], spans: list[Span], k: int, tolerance: float = DEFAULT_TOLERANCE_SECONDS) -> float:
    _require(spans, k)
    for chunk in ranked[:k]:
        if any(span.start - tolerance <= chunk.start <= span.end + tolerance for span in spans):
            return 1.0
    return 0.0


def _require(spans: list[Span], k: int) -> None:
    if not spans:
        raise ValueError("Retrieval metrics need at least one gold span (only answerable questions are scored).")
    if k < 1:
        raise ValueError("k must be at least 1.")


def score_question(ranked: list[Retrieved], spans: list[Span], ks: list[int], tolerance: float) -> dict:
    """All retrieval metrics for one question."""
    scores = {"mrr": reciprocal_rank(ranked, spans, tolerance)}
    for k in ks:
        scores[f"hit@{k}"] = hit_at_k(ranked, spans, k, tolerance)
        scores[f"recall@{k}"] = recall_at_k(ranked, spans, k, tolerance)
        scores[f"timestamp_hit@{k}"] = timestamp_hit_at_k(ranked, spans, k, tolerance)
    return scores


def aggregate(per_question: list[dict]) -> dict:
    """Means over scored questions, with n. Empty input gives n=0 and no values."""
    if not per_question:
        return {"n": 0}
    keys = per_question[0].keys()
    return {"n": len(per_question), **{key: fmean(scores[key] for scores in per_question) for key in keys}}
