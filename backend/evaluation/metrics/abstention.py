"""Abstention, citation coverage and citation support.

Inputs are per-question records with the dataset's gold `answerable` flag and the
system's `outcome` ("answered" or "insufficient_evidence"); citation-support labels come
only from annotation (human or a recorded judge), never from the system itself.

* Abstention precision: unanswerable / refused (how often a refusal was right).
* Abstention recall: refused unanswerable / all unanswerable.
* False-refusal rate: refused answerable / all answerable.
* Answered-unanswerable rate: answered unanswerable / all unanswerable (= 1 - recall).
* Citation coverage: answered with >= 1 cited source / answered. Coverage says nothing
  about whether the citations support the answer ("Cite or Decline" keeps these apart).
* Citation support: distribution of labels {full, partial, none} over *labelled* answered
  questions, plus how many answered questions are still unlabelled.
* Unsupported-answer rate: answered questions labelled "none" / labelled answered questions.

Any rate whose denominator is zero is None (not 0), so missing data is never shown as a result.
"""

ANSWERED = "answered"
REFUSED = "insufficient_evidence"
SUPPORT_LABELS = ("full", "partial", "none")


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def abstention(records: list[dict]) -> dict:
    answerable = [r for r in records if r["answerable"]]
    unanswerable = [r for r in records if not r["answerable"]]
    refused = [r for r in records if r["outcome"] == REFUSED]
    refused_unanswerable = sum(1 for r in unanswerable if r["outcome"] == REFUSED)
    refused_answerable = sum(1 for r in answerable if r["outcome"] == REFUSED)
    return {
        "n": len(records),
        "n_answerable": len(answerable),
        "n_unanswerable": len(unanswerable),
        "n_refused": len(refused),
        "abstention_precision": _rate(refused_unanswerable, len(refused)),
        "abstention_recall": _rate(refused_unanswerable, len(unanswerable)),
        "false_refusal_rate": _rate(refused_answerable, len(answerable)),
        "answered_unanswerable_rate": _rate(len(unanswerable) - refused_unanswerable, len(unanswerable)),
    }


def citation_coverage(records: list[dict]) -> dict:
    answered = [r for r in records if r["outcome"] == ANSWERED]
    cited = sum(1 for r in answered if any(source.get("cited") for source in r.get("sources") or []))
    return {"n_answered": len(answered), "citation_coverage": _rate(cited, len(answered))}


def citation_support(records: list[dict], labels: dict[str, str]) -> dict:
    """`labels` maps question_id -> support label for answered questions."""
    for label in labels.values():
        if label not in SUPPORT_LABELS:
            raise ValueError(f"Unknown citation-support label {label!r}; expected one of {SUPPORT_LABELS}.")
    answered = [r["question_id"] for r in records if r["outcome"] == ANSWERED]
    labelled = [labels[qid] for qid in answered if qid in labels]
    counts = {label: labelled.count(label) for label in SUPPORT_LABELS}
    return {
        "n_answered": len(answered),
        "n_labelled": len(labelled),
        "n_unlabelled": len(answered) - len(labelled),
        **{f"support_{label}": _rate(counts[label], len(labelled)) for label in SUPPORT_LABELS},
        "support_full_or_partial": _rate(counts["full"] + counts["partial"], len(labelled)),
        "unsupported_answer_rate": _rate(counts["none"], len(labelled)),
    }
