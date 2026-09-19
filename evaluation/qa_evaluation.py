"""
QA correctness / grounding and response-latency evaluation for the
LectureMind RAG chatbot.

Because "correctness" for open-ended answers cannot be fully automated
without human judgement or an additional LLM-as-judge (which this script
does not assume you have configured), this script does the following,
which is a defensible, honest evaluation approach for a minor project:

1. Calls the LectureMind chatbot for each gold question (via the backend's
   own RAG service, no HTTP server required).
2. Records the generated answer, whether it was grounded (i.e. not the
   "could not find" fallback), the retrieved sources, and response latency.
3. Compares the generated answer to a reference answer using ROUGE-L as a
   proxy lexical-overlap correctness signal (reported alongside, not
   presented as ground truth correctness).
4. Reports latency statistics (mean, min, max) across all questions.

For rigorous correctness evaluation, combine this script's output with a
manual review pass by the student/professor, which is standard practice
for evaluating open-domain QA systems.

Usage:
    cd backend
    python ../evaluation/qa_evaluation.py --lecture_id abc123 --gold_json ../evaluation/sample_data/gold_qa.json

gold_qa.json format:
[
  {"question": "What is supervised learning?", "reference_answer": "Supervised learning is ..."},
  ...
]
"""
import argparse
import json
import sys
import os
import time


def add_backend_to_path():
    here = os.path.dirname(os.path.abspath(__file__))
    backend_path = os.path.abspath(os.path.join(here, "..", "backend"))
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


def lexical_overlap_score(reference: str, hypothesis: str) -> float:
    """Lightweight ROUGE-L-style overlap score used only as a rough correctness proxy."""
    try:
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
        return scorer.score(reference, hypothesis)["rougeL"].fmeasure
    except ImportError:
        # Fallback: simple word-overlap ratio if rouge-score isn't installed.
        ref_words = set(reference.lower().split())
        hyp_words = set(hypothesis.lower().split())
        if not ref_words:
            return 0.0
        return len(ref_words & hyp_words) / len(ref_words)


def main():
    parser = argparse.ArgumentParser(description="Evaluate LectureMind RAG QA correctness/grounding and latency.")
    parser.add_argument("--lecture_id", required=True)
    parser.add_argument("--gold_json", required=True)
    args = parser.parse_args()

    add_backend_to_path()
    from app.services.rag import answer_question  # noqa: E402

    with open(args.gold_json, "r", encoding="utf-8") as f:
        gold_items = json.load(f)

    results = []
    latencies = []

    for item in gold_items:
        question = item["question"]
        reference = item.get("reference_answer", "")

        t0 = time.time()
        result = answer_question(args.lecture_id, question)
        wall_latency_ms = round((time.time() - t0) * 1000, 1)
        latencies.append(wall_latency_ms)

        overlap = lexical_overlap_score(reference, result["answer"]) if reference else None

        results.append({
            "question": question,
            "generated_answer": result["answer"],
            "grounded": result["grounded"],
            "reported_latency_ms": result["latency_ms"],
            "wall_clock_latency_ms": wall_latency_ms,
            "num_sources": len(result["sources"]),
            "lexical_overlap_with_reference": overlap,
        })

    summary = {
        "num_questions": len(gold_items),
        "grounded_ratio": sum(1 for r in results if r["grounded"]) / len(results) if results else 0.0,
        "average_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "min_latency_ms": min(latencies) if latencies else 0.0,
        "max_latency_ms": max(latencies) if latencies else 0.0,
        "results": results,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
