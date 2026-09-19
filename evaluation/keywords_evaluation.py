"""
Keyword extraction evaluation using Precision, Recall and F1-score against
a manually annotated reference keyword list.

Matching is done on lowercased, whitespace-normalised strings, since exact
LLM-generated keyword phrasing may vary slightly from the reference list
(e.g. "Machine Learning" vs "machine learning").

Usage:
    python keywords_evaluation.py --reference_json path/to/reference_keywords.json --hypothesis_json path/to/generated_keywords.json

Both JSON files should simply be a list of strings, e.g.:
["Machine Learning", "Supervised Learning", "Regression"]
"""
import argparse
import json


def normalize(kw: str) -> str:
    return " ".join(kw.lower().strip().split())


def compute_prf(reference: list, hypothesis: list) -> dict:
    ref_set = {normalize(k) for k in reference}
    hyp_set = {normalize(k) for k in hypothesis}

    tp = len(ref_set & hyp_set)
    precision = tp / len(hyp_set) if hyp_set else 0.0
    recall = tp / len(ref_set) if ref_set else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": tp,
        "reference_count": len(ref_set),
        "hypothesis_count": len(hyp_set),
        "matched_keywords": sorted(ref_set & hyp_set),
        "missed_keywords": sorted(ref_set - hyp_set),
        "extra_keywords": sorted(hyp_set - ref_set),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate LectureMind keyword extraction with Precision/Recall/F1.")
    parser.add_argument("--reference_json", required=True, help="Path to JSON list of reference (gold) keywords.")
    parser.add_argument("--hypothesis_json", required=True, help="Path to JSON list of LectureMind-generated keywords.")
    args = parser.parse_args()

    with open(args.reference_json, "r", encoding="utf-8") as f:
        reference = json.load(f)
    with open(args.hypothesis_json, "r", encoding="utf-8") as f:
        hypothesis = json.load(f)

    print(json.dumps(compute_prf(reference, hypothesis), indent=2))


if __name__ == "__main__":
    main()
