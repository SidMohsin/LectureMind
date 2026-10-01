"""Latency summaries over measured values (milliseconds). Missing values are skipped and counted."""

import math
from statistics import fmean, median


def percentile(sorted_values: list[float], fraction: float) -> float:
    """Nearest-rank percentile on pre-sorted values: the ceil(fraction * n)-th smallest value."""
    rank = max(1, math.ceil(fraction * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def summarize(values: list[float | int | None]) -> dict:
    measured = sorted(float(v) for v in values if v is not None)
    if not measured:
        return {"n": 0, "missing": len(values)}
    return {
        "n": len(measured),
        "missing": len(values) - len(measured),
        "mean": fmean(measured),
        "median": median(measured),
        "p90": percentile(measured, 0.90),
        "p95": percentile(measured, 0.95),
        "min": measured[0],
        "max": measured[-1],
    }
