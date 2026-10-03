"""LectureMind offline evaluation CLI (run from backend/: python -m evaluation.cli <command>).

  validate <dataset.json>                       check a dataset file and print its content hash
  run <dataset.json> --mode retrieval|answer    run a configuration; --set key=value overrides,
      [--sweep key=v1,v2,...]                   --sweep runs one configuration per value
      [--no-threshold --no-model-answerable --no-citation-check]   abstention-stage ablations
  score <run_dir> <dataset.json>                recompute summary.json from results + judgments
  rerun-check <run_dir> <dataset.json>          repeat retrieval and compare with the stored run
  annotation-template <run_dir> <dataset.json> <out.csv>   blank human-labelling sheet
  import-labels <run_dir> <labels.csv>          store human labels (correctness, citation support)
  judge <run_dir> <dataset.json>                secondary LLM correctness judge (EVAL_JUDGE_*)
  agreement <run_dir> --kind K --a ID --b ID    Cohen's kappa between two judges/annotators
  wer --reference ref.txt --lecture-id ID [--start s --end e] [--text cleaned|raw]
  timings --lecture-id ID [...]                 stage processing times (+ Q&A latency) as JSON
  asr librispeech|tedlium <file> --limit N      ASR WER/CER with the production transcriber; smoke
      [--purpose smoke|benchmark] [--error-probe]   runs by default (benchmark = whole split)
  asr-compare <run_dir_a> <run_dir_b>           determinism check between two ASR runs

Example datasets (kind: example) produce output labelled EXAMPLE; it is never a research result.
"""

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.intelligence.embeddings import FastEmbedEmbedder
from app.services import rag
from app.services.llm import OpenAICompatibleProvider
from app.services.supabase_admin import ServiceSupabase
from evaluation import config as config_module
from evaluation import runner
from evaluation.dataset import DatasetPolicyError, check_run_policy, load_dataset
from evaluation.judges import CorrectnessJudge, judge_settings
from evaluation.metrics import wer as wer_metrics
from evaluation.metrics.judgments import cohen_kappa
from evaluation.metrics.latency import summarize
from evaluation.results import DEFAULT_RUNS_DIR, JudgeInfo, Judgment, RunStore

EXAMPLE_BANNER = "EXAMPLE DATA - format/tooling check only, NOT a research result."


def _print(data) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _pairs(values: list[str]) -> dict[str, str]:
    out = {}
    for item in values or []:
        key, _, value = item.partition("=")
        if not value:
            raise SystemExit(f"Expected key=value, got {item!r}")
        out[key.strip()] = value.strip()
    return out


async def cmd_run(args) -> None:
    dataset = load_dataset(args.dataset)
    overrides = _pairs(args.set)
    sweep_key, sweep_values = None, [None]
    if args.sweep:
        sweep_key, _, raw = args.sweep.partition("=")
        sweep_values = [v.strip() for v in raw.split(",") if v.strip()]
    try:
        check_run_policy(dataset, sweep=len(sweep_values) > 1)
    except DatasetPolicyError as error:
        raise SystemExit(str(error)) from None
    abstention = rag.Abstention(
        use_threshold=not args.no_threshold,
        use_model_answerable=not args.no_model_answerable,
        require_valid_citations=not args.no_citation_check,
    )
    base = get_settings()
    async with httpx.AsyncClient(timeout=180) as http:
        admin = ServiceSupabase(http, base)
        lectures = await runner.resolve_lectures(admin, dataset, base)
        embedder = FastEmbedEmbedder(base)
        for value in sweep_values:
            run_overrides = {**overrides, **({sweep_key: value} if sweep_key else {})}
            settings, parsed = config_module.apply_overrides(base, run_overrides)
            provider = OpenAICompatibleProvider(http, settings) if args.mode == "answer" and settings.llm_configured else None
            experiment = config_module.capture(
                name=args.name, mode=args.mode, settings=settings, overrides=parsed, dataset=dataset,
                abstention=abstention, ks=args.k, tolerance_seconds=args.tolerance, lectures=list(lectures.values()),
            )
            store = RunStore.create(Path(args.out), experiment.run_id)
            store.write_config(experiment.model_dump(mode="json"))
            await runner.run(dataset, lectures, store, mode=args.mode, admin=admin, embedder=embedder,
                             provider=provider, settings=settings, abstention=abstention)
            summary = runner.score(store, dataset)
            if dataset.is_example:
                print(EXAMPLE_BANNER)
            _print({"run_dir": str(store.directory), "config_hash": experiment.config_hash, "summary": summary})


def cmd_score(args) -> None:
    dataset = load_dataset(args.dataset)
    summary = runner.score(RunStore(Path(args.run_dir)), dataset)
    if summary["example_data"]:
        print(EXAMPLE_BANNER)
    _print(summary)


async def cmd_rerun(args) -> None:
    dataset = load_dataset(args.dataset)
    store = RunStore(Path(args.run_dir))
    stored = store.config()
    base = get_settings()
    settings, _ = config_module.apply_overrides(base, {k: str(v) for k, v in stored["overrides"].items()})
    if settings.embedding_model != stored["embedding"]["model"]:
        raise SystemExit("The configured embedding model differs from the stored run's.")
    async with httpx.AsyncClient(timeout=120) as http:
        report = await runner.rerun_check(store, dataset, admin=ServiceSupabase(http, base), embedder=FastEmbedEmbedder(base), settings=settings)
    _print(report)


def cmd_template(args) -> None:
    dataset = load_dataset(args.dataset)
    store = RunStore(Path(args.run_dir))
    by_id = {q.question_id: q for q in dataset.questions}
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run_id", "question_id", "answerable", "question", "reference_answer", "outcome", "generated_answer",
                         "cited_passages", "correctness_label", "citation_support_label", "annotator", "notes"])
        for record in store.results():
            question = by_id[record["question_id"]]
            cited = " || ".join(f"[{s['start_seconds']:.0f}-{s['end_seconds']:.0f}s] {s['text']}"
                                for s in record.get("sources") or [] if s.get("cited"))
            writer.writerow([record["run_id"], record["question_id"], question.answerable, question.question,
                             question.reference_answer or "", record.get("outcome"), record.get("answer") or "", cited,
                             "", "", "", ""])
    print(f"Wrote {args.out}. Labels: correctness = correct|partially_correct|incorrect; "
          "citation_support = full|partial|none (answered questions only).")


def cmd_import(args) -> None:
    store = RunStore(Path(args.run_dir))
    judgments = []
    with open(args.labels, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            annotator = (row.get("annotator") or "").strip()
            for kind, column in (("correctness", "correctness_label"), ("citation_support", "citation_support_label")):
                label = (row.get(column) or "").strip()
                if not label:
                    continue
                if not annotator:
                    raise SystemExit(f"{row['question_id']}: a label needs an annotator id.")
                judgments.append(Judgment(run_id=row["run_id"], question_id=row["question_id"], kind=kind, label=label,
                                          rationale=(row.get("notes") or None), judge=JudgeInfo(type="human", id=annotator)))
    store.append_judgments(judgments)
    print(f"Stored {len(judgments)} human label(s).")


async def cmd_judge(args) -> None:
    dataset = load_dataset(args.dataset)
    store = RunStore(Path(args.run_dir))
    settings = judge_settings(get_settings(), allow_same_model=args.allow_same_model)
    by_id = {q.question_id: q for q in dataset.questions}
    async with httpx.AsyncClient(timeout=180) as http:
        judge = CorrectnessJudge(OpenAICompatibleProvider(http, settings), settings.llm_temperature)
        judgments = []
        for record in store.results():
            question = by_id[record["question_id"]]
            judgment = await judge.judge(record, question.question, question.reference_answer or "")
            if judgment:
                judgments.append(judgment)
    store.append_judgments(judgments)
    print(f"Stored {len(judgments)} secondary LLM judgment(s) from {settings.llm_model}. These are not ground truth.")


def cmd_agreement(args) -> None:
    store = RunStore(Path(args.run_dir))
    judgments = [j for j in store.judgments() if j.kind == args.kind]
    first = {j.question_id: j.label for j in judgments if j.judge.id == args.a}
    second = {j.question_id: j.label for j in judgments if j.judge.id == args.b}
    _print({"kind": args.kind, "a": args.a, "b": args.b, **cohen_kappa(first, second)})


async def cmd_wer(args) -> None:
    reference = Path(args.reference).read_text(encoding="utf-8")
    settings = get_settings()
    async with httpx.AsyncClient(timeout=60) as http:
        admin = ServiceSupabase(http, settings)
        segments = await admin.select_all(
            "transcript_segments",
            {"select": "sequence,start_seconds,end_seconds,raw_text,text", "lecture_id": f"eq.{args.lecture_id}", "order": "sequence"},
        )
        transcript = await admin.select("transcripts", {"select": "model,model_config", "lecture_id": f"eq.{args.lecture_id}"})
    if args.start is not None or args.end is not None:
        start, end = args.start or 0.0, args.end if args.end is not None else float("inf")
        # A segment belongs to the range when its midpoint does (documented, deterministic).
        segments = [s for s in segments if start <= (float(s["start_seconds"]) + float(s["end_seconds"])) / 2 < end]
    column = "raw_text" if args.text == "raw" else "text"
    hypothesis = " ".join((s[column] or "") for s in segments)
    _print({
        "normalizer": wer_metrics.NORMALIZER_VERSION,
        "lecture_id": args.lecture_id,
        "hypothesis_text": args.text,
        "range_seconds": [args.start, args.end],
        "segments": len(segments),
        "asr": transcript[0] if transcript else None,
        "wer": wer_metrics.wer(reference, hypothesis).as_dict(),
        "cer": wer_metrics.cer(reference, hypothesis).as_dict(),
    })


async def cmd_timings(args) -> None:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=60) as http:
        admin = ServiceSupabase(http, settings)
        stages, questions = {}, []
        for lecture_id in args.lecture_id:
            jobs = await admin.select("processing_jobs", {"select": "id", "lecture_id": f"eq.{lecture_id}"})
            for job in jobs:
                runs = await admin.select_all(
                    "processing_stage_runs",
                    {"select": "stage,attempt,status,duration_ms", "job_id": f"eq.{job['id']}", "order": "started_at"},
                )
                for run in runs:
                    if run["status"] == "succeeded":
                        stages.setdefault(run["stage"], []).append(run["duration_ms"])
            if args.questions:
                # Timing columns only: no question or answer text leaves the database.
                questions += await admin.select_all(
                    "chat_logs", {"select": "outcome,retrieval_ms,llm_ms,latency_ms", "lecture_id": f"eq.{lecture_id}", "order": "created_at"}
                )
    report = {"lectures": args.lecture_id, "stage_duration_ms": {stage: summarize(values) for stage, values in stages.items()}}
    if args.questions:
        report["questions"] = {key: summarize([q[key] for q in questions]) for key in ("retrieval_ms", "llm_ms", "latency_ms")}
    _print(report)


def cmd_asr(args) -> None:
    import tempfile

    from app.intelligence.transcription import FasterWhisperTranscriber
    from evaluation import asr_benchmark

    if args.purpose == "smoke":
        print(asr_benchmark.SMOKE_LABEL)
    with tempfile.TemporaryDirectory(prefix="lecturemind-asr-") as workdir:
        directory = asr_benchmark.run(
            source=args.source,
            dataset_path=Path(args.file),
            out_root=Path(args.out),
            transcriber=FasterWhisperTranscriber(get_settings()),
            purpose=args.purpose,
            limit=args.limit,
            error_probe_item=args.error_probe,
            seed=args.seed,
            workdir=Path(workdir),
        )
    if args.purpose == "smoke":
        print(asr_benchmark.SMOKE_LABEL)
    print(f"run directory: {directory}")
    _print(json.loads((directory / "summary.json").read_text(encoding="utf-8")))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m evaluation.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate")
    p.add_argument("dataset")

    p = sub.add_parser("run")
    p.add_argument("dataset")
    p.add_argument("--mode", choices=["retrieval", "answer"], required=True)
    p.add_argument("--name", default="unnamed")
    p.add_argument("--set", action="append", default=[])
    p.add_argument("--sweep")
    p.add_argument("--k", type=int, nargs="+", default=[1, 3, 5])
    p.add_argument("--tolerance", type=float, default=30.0)
    p.add_argument("--no-threshold", action="store_true")
    p.add_argument("--no-model-answerable", action="store_true")
    p.add_argument("--no-citation-check", action="store_true")
    p.add_argument("--out", default=str(DEFAULT_RUNS_DIR))

    for name in ("score", "rerun-check"):
        p = sub.add_parser(name)
        p.add_argument("run_dir")
        p.add_argument("dataset")

    p = sub.add_parser("annotation-template")
    p.add_argument("run_dir")
    p.add_argument("dataset")
    p.add_argument("out")

    p = sub.add_parser("import-labels")
    p.add_argument("run_dir")
    p.add_argument("labels")

    p = sub.add_parser("judge")
    p.add_argument("run_dir")
    p.add_argument("dataset")
    p.add_argument("--allow-same-model", action="store_true")

    p = sub.add_parser("agreement")
    p.add_argument("run_dir")
    p.add_argument("--kind", choices=["correctness", "citation_support"], required=True)
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)

    p = sub.add_parser("wer")
    p.add_argument("--reference", required=True)
    p.add_argument("--lecture-id", required=True)
    p.add_argument("--start", type=float)
    p.add_argument("--end", type=float)
    p.add_argument("--text", choices=["cleaned", "raw"], default="cleaned")

    p = sub.add_parser("timings")
    p.add_argument("--lecture-id", action="append", required=True)
    p.add_argument("--questions", action="store_true")

    p = sub.add_parser("asr")
    p.add_argument("source", choices=["librispeech", "tedlium"])
    p.add_argument("file", help="LibriSpeech test-*.tar.gz or the TED-LIUM test .parquet")
    p.add_argument("--purpose", choices=["smoke", "benchmark"], default="smoke")
    p.add_argument("--limit", type=int)
    p.add_argument("--error-probe", action="store_true", help="smoke only: add one undecodable file")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=str(DEFAULT_RUNS_DIR / "asr"))

    p = sub.add_parser("asr-compare")
    p.add_argument("run_a")
    p.add_argument("run_b")

    args = parser.parse_args(argv)
    if args.command == "validate":
        dataset = load_dataset(args.dataset)
        answerable = sum(1 for q in dataset.questions if q.answerable)
        if dataset.is_example:
            print(EXAMPLE_BANNER)
        _print({"dataset_id": dataset.dataset_id, "version": dataset.version, "kind": dataset.kind, "split": dataset.split,
                "frozen": dataset.frozen, "questions": len(dataset.questions), "answerable": answerable,
                "unanswerable": len(dataset.questions) - answerable, "content_sha256": dataset.content_hash()})
    elif args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "score":
        cmd_score(args)
    elif args.command == "rerun-check":
        asyncio.run(cmd_rerun(args))
    elif args.command == "annotation-template":
        cmd_template(args)
    elif args.command == "import-labels":
        cmd_import(args)
    elif args.command == "judge":
        asyncio.run(cmd_judge(args))
    elif args.command == "agreement":
        cmd_agreement(args)
    elif args.command == "wer":
        asyncio.run(cmd_wer(args))
    elif args.command == "timings":
        asyncio.run(cmd_timings(args))
    elif args.command == "asr":
        cmd_asr(args)
    elif args.command == "asr-compare":
        from evaluation.asr_benchmark import compare

        _print(compare(Path(args.run_a), Path(args.run_b)))


if __name__ == "__main__":
    main()
