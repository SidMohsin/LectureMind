"""Answer correctness from judgments, and agreement between annotators.

Correctness labels: correct | partially_correct | incorrect. Human judgments are the
authoritative route; LLM-judge results are reported separately and never merged with
human labels. Agreement between two annotators (or a human and a judge) uses Cohen's kappa
over the questions both labelled.
"""

from collections import Counter

CORRECTNESS_LABELS = ("correct", "partially_correct", "incorrect")


def correctness(labels: dict[str, str]) -> dict:
    for label in labels.values():
        if label not in CORRECTNESS_LABELS:
            raise ValueError(f"Unknown correctness label {label!r}; expected one of {CORRECTNESS_LABELS}.")
    n = len(labels)
    counts = Counter(labels.values())
    return {"n_labelled": n, **{label: (counts[label] / n if n else None) for label in CORRECTNESS_LABELS}}


def cohen_kappa(first: dict[str, str], second: dict[str, str]) -> dict:
    """Cohen's kappa over items labelled by both raters."""
    shared = sorted(set(first) & set(second))
    n = len(shared)
    if n == 0:
        return {"n": 0, "agreement": None, "kappa": None}
    observed = sum(1 for item in shared if first[item] == second[item]) / n
    a, b = Counter(first[i] for i in shared), Counter(second[i] for i in shared)
    expected = sum((a[label] / n) * (b[label] / n) for label in set(a) | set(b))
    kappa = None if expected == 1 else (observed - expected) / (1 - expected)
    return {"n": n, "agreement": observed, "kappa": kappa}
