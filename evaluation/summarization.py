"""
Summarization quality evaluation using ROUGE and BERTScore.

Usage:
    python summarization.py --reference path/to/reference_summary.txt --hypothesis path/to/lecturemind_summary.txt
    python summarization.py --pairs_json path/to/pairs.json

pairs.json format:
[
  {"id": "lecture_1", "reference": "reference summary ...", "hypothesis": "generated summary ..."},
  ...
]

Requires: pip install rouge-score bert-score
"""
import argparse
import json
import sys


def compute_rouge(reference: str, hypothesis: str) -> dict:
    try:
        from rouge_score import rouge_scorer
    except ImportError:
        print("ERROR: rouge-score is not installed. Run: pip install rouge-score", file=sys.stderr)
        sys.exit(1)

    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
    scores = scorer.score(reference, hypothesis)
    return {
        key: {"precision": val.precision, "recall": val.recall, "f1": val.fmeasure}
        for key, val in scores.items()
    }


def compute_bertscore(references: list, hypotheses: list) -> dict:
    try:
        from bert_score import score as bertscore_score
    except ImportError:
        print("ERROR: bert-score is not installed. Run: pip install bert-score", file=sys.stderr)
        sys.exit(1)

    P, R, F1 = bertscore_score(hypotheses, references, lang="en", verbose=False)
    return {
        "precision": P.mean().item(),
        "recall": R.mean().item(),
        "f1": F1.mean().item(),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate LectureMind summarization output with ROUGE and BERTScore.")
    parser.add_argument("--reference", type=str, help="Path to a text file with the reference summary.")
    parser.add_argument("--hypothesis", type=str, help="Path to a text file with LectureMind's generated summary.")
    parser.add_argument("--pairs_json", type=str, help="Path to a JSON file with multiple reference/hypothesis pairs.")
    parser.add_argument("--skip_bertscore", action="store_true", help="Skip BERTScore (it downloads a BERT model and can be slow on CPU).")
    args = parser.parse_args()

    if args.pairs_json:
        with open(args.pairs_json, "r", encoding="utf-8") as f:
            pairs = json.load(f)
        refs = [p["reference"] for p in pairs]
        hyps = [p["hypothesis"] for p in pairs]

        rouge_results = []
        for p in pairs:
            r = compute_rouge(p["reference"], p["hypothesis"])
            r["id"] = p.get("id", "unknown")
            rouge_results.append(r)

        output = {"rouge": rouge_results}
        if not args.skip_bertscore:
            output["bertscore_average"] = compute_bertscore(refs, hyps)
        print(json.dumps(output, indent=2))

    elif args.reference and args.hypothesis:
        with open(args.reference, "r", encoding="utf-8") as f:
            ref = f.read()
        with open(args.hypothesis, "r", encoding="utf-8") as f:
            hyp = f.read()

        output = {"rouge": compute_rouge(ref, hyp)}
        if not args.skip_bertscore:
            output["bertscore"] = compute_bertscore([ref], [hyp])
        print(json.dumps(output, indent=2))
    else:
        parser.error("Provide either --reference and --hypothesis, or --pairs_json.")


if __name__ == "__main__":
    main()
