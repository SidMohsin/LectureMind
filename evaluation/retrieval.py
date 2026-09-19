"""
Retrieval evaluation: Recall@k and Precision@k for the ChromaDB semantic
retriever used by LectureMind's RAG chatbot.

This script expects a "gold" mapping of queries to the set of chunk_ids
(or timestamp ranges) that are actually relevant to that query, and compares
it against what LectureMind's retriever actually returns.

Usage:
    python retrieval.py --lecture_id <id> --gold_json path/to/gold.json --k 5

gold.json format:
[
  {
    "query": "What is supervised learning?",
    "relevant_chunk_ids": ["<lecture_id>_chunk_3", "<lecture_id>_chunk_4"]
  },
  ...
]

This script calls into the backend's own retrieval service directly
(no HTTP server required) so it must be run from within the backend's
Python environment, with the backend/ directory on PYTHONPATH.

Example (from the LectureMind root):
    cd backend
    python ../evaluation/retrieval.py --lecture_id abc123 --gold_json ../evaluation/sample_data/gold_retrieval.json --k 5
"""
import argparse
import json
import sys
import os


def add_backend_to_path():
    # Allow running this script from evaluation/ while importing the backend's app package.
    here = os.path.dirname(os.path.abspath(__file__))
    backend_path = os.path.join(here, "..", "backend")
    backend_path = os.path.abspath(backend_path)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


def recall_at_k(retrieved_ids: list, relevant_ids: set) -> float:
    if not relevant_ids:
        return 0.0
    retrieved_set = set(retrieved_ids)
    hits = len(retrieved_set & relevant_ids)
    return hits / len(relevant_ids)


def precision_at_k(retrieved_ids: list, relevant_ids: set) -> float:
    if not retrieved_ids:
        return 0.0
    retrieved_set = set(retrieved_ids)
    hits = len(retrieved_set & relevant_ids)
    return hits / len(retrieved_ids)


def main():
    parser = argparse.ArgumentParser(description="Evaluate LectureMind's semantic retrieval with Recall@k / Precision@k.")
    parser.add_argument("--lecture_id", required=True, help="Lecture ID that has already been processed and indexed.")
    parser.add_argument("--gold_json", required=True, help="Path to gold query -> relevant_chunk_ids JSON file.")
    parser.add_argument("--k", type=int, default=5, help="Top-k value to evaluate.")
    args = parser.parse_args()

    add_backend_to_path()
    from app.services.retrieval import retrieve_relevant_chunks  # noqa: E402

    with open(args.gold_json, "r", encoding="utf-8") as f:
        gold_items = json.load(f)

    results = []
    total_recall = 0.0
    total_precision = 0.0

    for item in gold_items:
        query = item["query"]
        relevant_ids = set(item["relevant_chunk_ids"])

        retrieved = retrieve_relevant_chunks(args.lecture_id, query, top_k=args.k)
        retrieved_ids = [r["chunk_id"] for r in retrieved]

        r = recall_at_k(retrieved_ids, relevant_ids)
        p = precision_at_k(retrieved_ids, relevant_ids)
        total_recall += r
        total_precision += p

        results.append({
            "query": query,
            "retrieved_ids": retrieved_ids,
            "relevant_ids": list(relevant_ids),
            f"recall@{args.k}": r,
            f"precision@{args.k}": p,
        })

    n = len(gold_items) or 1
    summary = {
        "k": args.k,
        "num_queries": len(gold_items),
        f"average_recall@{args.k}": total_recall / n,
        f"average_precision@{args.k}": total_precision / n,
        "results": results,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
