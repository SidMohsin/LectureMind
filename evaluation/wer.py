"""
Word Error Rate (WER) evaluation for the Whisper transcription component.

Usage:
    python wer.py --reference path/to/reference.txt --hypothesis path/to/hypothesis.txt
    python wer.py --pairs_json path/to/pairs.json

pairs.json format (for evaluating multiple lecture recordings at once):
[
  {"id": "lecture_1", "reference": "reference text ...", "hypothesis": "transcribed text ..."},
  ...
]

Requires: pip install jiwer
"""
import argparse
import json
import sys


def compute_wer(reference: str, hypothesis: str) -> dict:
    try:
        import jiwer
    except ImportError:
        print("ERROR: jiwer is not installed. Run: pip install jiwer", file=sys.stderr)
        sys.exit(1)

    transform = jiwer.Compose([
        jiwer.ToLowerCase(),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.RemovePunctuation(),
        jiwer.ReduceToListOfListOfWords(),
    ])

    measures = jiwer.compute_measures(
        reference, hypothesis,
        truth_transform=transform, hypothesis_transform=transform,
    )
    return {
        "wer": measures["wer"],
        "substitutions": measures["substitutions"],
        "deletions": measures["deletions"],
        "insertions": measures["insertions"],
        "hits": measures["hits"],
    }


def main():
    parser = argparse.ArgumentParser(description="Compute WER for LectureMind transcription output.")
    parser.add_argument("--reference", type=str, help="Path to a text file with the ground-truth transcript.")
    parser.add_argument("--hypothesis", type=str, help="Path to a text file with LectureMind's transcript output.")
    parser.add_argument("--pairs_json", type=str, help="Path to a JSON file with multiple reference/hypothesis pairs.")
    args = parser.parse_args()

    if args.pairs_json:
        with open(args.pairs_json, "r", encoding="utf-8") as f:
            pairs = json.load(f)
        results = []
        total_wer = 0.0
        for pair in pairs:
            result = compute_wer(pair["reference"], pair["hypothesis"])
            result["id"] = pair.get("id", "unknown")
            results.append(result)
            total_wer += result["wer"]
        avg_wer = total_wer / len(pairs) if pairs else 0.0
        print(json.dumps({"results": results, "average_wer": avg_wer}, indent=2))

    elif args.reference and args.hypothesis:
        with open(args.reference, "r", encoding="utf-8") as f:
            ref = f.read()
        with open(args.hypothesis, "r", encoding="utf-8") as f:
            hyp = f.read()
        result = compute_wer(ref, hyp)
        print(json.dumps(result, indent=2))
    else:
        parser.error("Provide either --reference and --hypothesis, or --pairs_json.")


if __name__ == "__main__":
    main()
