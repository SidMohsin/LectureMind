"""Evaluation framework (Phase 7B).

ALL numbers in this file are hand-made UNIT-TEST FIXTURES that check metric arithmetic
and tooling behaviour. None of them is, or may be reported as, a research result.
"""

import csv
import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services import rag
from evaluation import config as config_module
from evaluation import runner
from evaluation.dataset import DatasetPolicyError, EvalDataset, check_run_policy, load_dataset
from evaluation.judges import JudgeConfigError, judge_settings
from evaluation.metrics import abstention, judgments, latency, retrieval, wer
from evaluation.results import JudgeInfo, Judgment, RunStore

pytestmark = pytest.mark.anyio

EXAMPLE = Path(__file__).resolve().parents[1] / "evaluation" / "examples" / "example_dataset.json"
EVAL_USER = "11111111-1111-1111-1111-111111111111"
LECTURE = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --- retrieval metrics (fixtures) -------------------------------------------------------------

R = retrieval.Retrieved
S = retrieval.Span


def test_relevance_uses_overlap_with_tolerance():
    span = [S(100, 130)]
    assert retrieval.is_relevant(R(120, 180), span, tolerance=0)
    assert not retrieval.is_relevant(R(131, 180), span, tolerance=0)
    assert retrieval.is_relevant(R(131, 180), span, tolerance=30)
    assert not retrieval.is_relevant(R(161, 200), span, tolerance=30)


def test_hit_recall_mrr_and_timestamp_hit():
    ranked = [R(0, 60), R(300, 360), R(110, 170), R(500, 560)]
    spans = [S(120, 140), S(510, 520)]
    assert retrieval.hit_at_k(ranked, spans, 1, tolerance=0) == 0.0
    assert retrieval.hit_at_k(ranked, spans, 3, tolerance=0) == 1.0
    assert retrieval.recall_at_k(ranked, spans, 3, tolerance=0) == 0.5
    assert retrieval.recall_at_k(ranked, spans, 4, tolerance=0) == 1.0
    assert retrieval.reciprocal_rank(ranked, spans, tolerance=0) == pytest.approx(1 / 3)
    # Chunk 3 starts at 110: outside [120,140] without tolerance, inside with 30 s.
    assert retrieval.timestamp_hit_at_k(ranked, spans, 3, tolerance=0) == 0.0
    assert retrieval.timestamp_hit_at_k(ranked, spans, 3, tolerance=30) == 1.0
    assert retrieval.reciprocal_rank([R(0, 10)], spans, tolerance=0) == 0.0


def test_retrieval_metrics_refuse_questions_without_gold_spans():
    with pytest.raises(ValueError):
        retrieval.hit_at_k([R(0, 1)], [], 1)


def test_aggregate_means_with_n():
    assert retrieval.aggregate([{"mrr": 1.0}, {"mrr": 0.0}]) == {"n": 2, "mrr": 0.5}
    assert retrieval.aggregate([]) == {"n": 0}


# --- WER (fixtures) ---------------------------------------------------------------------------


def test_normalizer_is_explicit():
    assert wer.normalize("Uh, so the [music] Learning-Rate (laughs) isn’t “fixed”!") == "so the learning rate isn't fixed"
    assert wer.NORMALIZER_VERSION == "lecturemind-wer-normalizer/v1"


def test_wer_counts_substitutions_deletions_insertions():
    # Unique minimal alignment: "b" deleted, "e" inserted (2 edits), not 3 substitutions.
    counts = wer.wer("a b c d", "a c d e")
    assert (counts.substitutions, counts.deletions, counts.insertions, counts.reference_length) == (0, 1, 1, 4)
    assert counts.rate == pytest.approx(2 / 4)
    swapped = wer.wer("the cat sat", "the dog sat")
    assert (swapped.substitutions, swapped.errors) == (1, 1)
    assert wer.wer("Hello, world.", "hello world").rate == 0.0
    assert wer.wer("", "words").rate is None  # no reference words: undefined, not 0 or infinity


def test_corpus_wer_sums_edits_not_rates():
    total = wer.corpus([("a b", "a x"), ("c d e f", "c d e f")])
    assert total.errors == 1 and total.reference_length == 6 and total.rate == pytest.approx(1 / 6)


def test_cer():
    assert wer.cer("abc", "abd").rate == pytest.approx(1 / 3)


# --- abstention / citations / judgments (fixtures) -------------------------------------------


def _record(qid, answerable, outcome, cited=True):
    return {"question_id": qid, "answerable": answerable, "outcome": outcome,
            "sources": [{"cited": cited}] if outcome == "answered" else []}


def test_abstention_metrics():
    records = [
        _record("a1", True, "answered"), _record("a2", True, "insufficient_evidence"),
        _record("u1", False, "insufficient_evidence"), _record("u2", False, "answered"), _record("u3", False, "insufficient_evidence"),
    ]
    m = abstention.abstention(records)
    assert m["abstention_precision"] == pytest.approx(2 / 3)
    assert m["abstention_recall"] == pytest.approx(2 / 3)
    assert m["false_refusal_rate"] == pytest.approx(1 / 2)
    assert m["answered_unanswerable_rate"] == pytest.approx(1 / 3)
    assert abstention.abstention([_record("a", True, "answered")])["abstention_precision"] is None


def test_citation_coverage_and_support_are_separate():
    records = [_record("q1", True, "answered"), _record("q2", True, "answered", cited=False), _record("q3", True, "answered")]
    assert abstention.citation_coverage(records)["citation_coverage"] == pytest.approx(2 / 3)
    support = abstention.citation_support(records, {"q1": "full", "q3": "none"})
    assert support["n_labelled"] == 2 and support["n_unlabelled"] == 1
    assert support["support_full"] == 0.5 and support["unsupported_answer_rate"] == 0.5
    empty = abstention.citation_support(records, {})
    assert empty["support_full"] is None and empty["unsupported_answer_rate"] is None  # no labels, no numbers
    with pytest.raises(ValueError):
        abstention.citation_support(records, {"q1": "mostly"})


def test_correctness_and_kappa():
    assert judgments.correctness({"a": "correct", "b": "incorrect"})["correct"] == 0.5
    assert judgments.correctness({})["correct"] is None
    result = judgments.cohen_kappa({"1": "x", "2": "x", "3": "y", "4": "y"}, {"1": "x", "2": "y", "3": "y", "4": "y"})
    assert result["n"] == 4 and result["agreement"] == 0.75 and result["kappa"] == pytest.approx(0.5)


def test_latency_summary_skips_missing_values():
    summary = latency.summarize([100, 200, None, 300, 400])
    assert summary["n"] == 4 and summary["missing"] == 1 and summary["median"] == 250 and summary["p90"] == 400
    assert latency.summarize([None]) == {"n": 0, "missing": 1}


# --- dataset format and policy ------------------------------------------------------------------


def _dataset(**overrides) -> EvalDataset:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data.update(overrides)
    return EvalDataset.model_validate(data)


def test_example_dataset_is_valid_and_marked():
    dataset = load_dataset(EXAMPLE)
    assert dataset.is_example and len(dataset.content_hash()) == 64
    assert {q.answerable for q in dataset.questions} == {True, False}


def test_dataset_validation_rules():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    broken = json.loads(json.dumps(data))
    broken["questions"][0]["gold_spans"] = []
    with pytest.raises(ValueError, match="gold spans"):
        EvalDataset.model_validate(broken)
    broken = json.loads(json.dumps(data))
    broken["questions"][1]["gold_spans"] = [{"start_seconds": 1, "end_seconds": 2}]
    with pytest.raises(ValueError, match="must not have gold spans"):
        EvalDataset.model_validate(broken)
    broken = json.loads(json.dumps(data))
    broken["questions"][1]["question_id"] = broken["questions"][0]["question_id"]
    with pytest.raises(ValueError, match="unique"):
        EvalDataset.model_validate(broken)
    broken = json.loads(json.dumps(data))
    broken["questions"][0]["gold_spans"] = [{"start_seconds": 50, "end_seconds": 40}]
    with pytest.raises(ValueError):
        EvalDataset.model_validate(broken)


def test_calibration_and_test_policy():
    check_run_policy(_dataset(split="calibration"), sweep=True)  # tuning allowed on calibration
    with pytest.raises(DatasetPolicyError, match="frozen"):
        check_run_policy(_dataset(split="test"), sweep=False)
    frozen = _dataset(split="test", frozen=True, frozen_at="2026-10-01T00:00:00Z")
    check_run_policy(frozen, sweep=False)
    with pytest.raises(DatasetPolicyError, match="sweeps"):
        check_run_policy(frozen, sweep=True)


def test_content_hash_changes_with_questions():
    a, b = _dataset(), _dataset()
    assert a.content_hash() == b.content_hash()
    b.questions[0].question = "EXAMPLE: a different question?"
    assert a.content_hash() != b.content_hash()


# --- configuration capture ----------------------------------------------------------------------


def test_overrides_are_whitelisted():
    settings, parsed = config_module.apply_overrides(Settings(_env_file=None), {"rag_top_k": "10", "rag_min_similarity": "0.5"})
    assert settings.rag_top_k == 10 and parsed == {"rag_top_k": 10, "rag_min_similarity": 0.5}
    with pytest.raises(ValueError):
        config_module.apply_overrides(Settings(_env_file=None), {"supabase_url": "x"})


def _capture(settings, **kwargs):
    return config_module.capture(
        name="unit", mode=kwargs.get("mode", "retrieval"), settings=settings, overrides={}, dataset=_dataset(),
        abstention=kwargs.get("abstention", rag.FULL_ABSTENTION), ks=[1, 3], tolerance_seconds=30.0, lectures=[],
    )


def test_config_capture_records_provenance_and_stable_hash():
    settings = Settings(_env_file=None, llm_model="gen-model", llm_base_url="https://llm.example/v1")
    first, second = _capture(settings), _capture(settings)
    assert first.run_id != second.run_id and first.config_hash == second.config_hash
    assert first.git["commit"] is None or len(first.git["commit"]) == 40
    assert first.dataset["content_sha256"] == _dataset().content_hash() and first.dataset["kind"] == "example"
    assert first.embedding == {"model": "BAAI/bge-small-en-v1.5", "dimension": 384}
    changed = _capture(settings.model_copy(update={"rag_top_k": 9}))
    assert changed.config_hash != first.config_hash
    ablation = _capture(settings, abstention=rag.Abstention(use_threshold=False))
    assert ablation.config_hash != first.config_hash
    answer = _capture(settings, mode="answer")
    assert answer.generator["prompt_version"] == rag.PROMPT_VERSION and len(answer.generator["system_prompt_sha256"]) == 64


# --- runner with fakes --------------------------------------------------------------------------


CHUNKS = [
    {"chunk_id": "c0", "sequence": 0, "start_seconds": 0, "end_seconds": 60, "similarity": 0.62, "text": "Intro to the course."},
    {"chunk_id": "c2", "sequence": 2, "start_seconds": 115, "end_seconds": 175, "similarity": 0.81, "text": "Gradient descent updates parameters."},
    {"chunk_id": "c7", "sequence": 7, "start_seconds": 420, "end_seconds": 480, "similarity": 0.41, "text": "Unrelated part."},
]


class EvalAdmin:
    def __init__(self, owner=EVAL_USER, status="READY", model="BAAI/bge-small-en-v1.5", rows=None):
        self.owner, self.status, self.model = owner, status, model
        self.rows = rows if rows is not None else [CHUNKS[1], CHUNKS[0], CHUNKS[2]]
        self.rpc_calls = []
        self.writes = []

    async def select(self, table, params):
        if table == "lectures":
            return [{"id": LECTURE, "user_id": self.owner, "status": self.status}]
        if table == "lecture_chunks":
            return [{"embedding_model": self.model}]
        if table == "transcripts":
            return [{"model": "faster-whisper/small", "model_config": {"beam_size": 5}, "language": "en"}]
        if table == "processing_jobs":
            return [{"id": "job-1"}]
        if table == "processing_stage_runs":
            return [{"details": {"config": {"min_tokens": 200, "max_tokens": 400, "overlap_tokens": 50}}}]
        raise AssertionError(table)

    async def rpc(self, function, args):
        self.rpc_calls.append((function, args))
        return [dict(row) for row in self.rows]

    async def insert(self, *args, **kwargs):  # the evaluator must never write to Supabase
        self.writes.append(args)
        raise AssertionError("evaluation wrote to the database")


class Embedder:
    name = "BAAI/bge-small-en-v1.5"
    dimension = 384

    def embed_query(self, text):
        return [0.01] * 384


class Provider:
    name = "gen.example"
    model = "gen-model"

    async def generate_json(self, system, user, *, max_tokens=4096):
        return {"answerable": True, "answer": "It updates the parameters.", "citations": [2]}


def _settings(**overrides):
    return Settings(_env_file=None, eval_user_id=EVAL_USER, rag_top_k=3, **overrides)


def _example_with_lecture():
    dataset = _dataset()
    dataset.lectures[0].lecture_id = LECTURE
    return dataset


async def test_lectures_outside_the_evaluation_account_are_refused():
    dataset = _example_with_lecture()
    with pytest.raises(runner.EvaluationSetupError, match="EVAL_USER_ID"):
        await runner.resolve_lectures(EvalAdmin(), dataset, Settings(_env_file=None))
    with pytest.raises(runner.EvaluationSetupError, match="not owned"):
        await runner.resolve_lectures(EvalAdmin(owner="someone-else"), dataset, _settings())
    with pytest.raises(runner.EvaluationSetupError, match="READY"):
        await runner.resolve_lectures(EvalAdmin(status="EMBEDDING"), dataset, _settings())
    with pytest.raises(runner.EvaluationSetupError, match="embedded"):
        await runner.resolve_lectures(EvalAdmin(model="other/model"), dataset, _settings())
    resolved = await runner.resolve_lectures(EvalAdmin(), dataset, _settings())
    assert resolved["example-lecture"]["asr"]["model"] == "faster-whisper/small"
    assert resolved["example-lecture"]["chunking"]["overlap_tokens"] == 50


async def _run(tmp_path, mode, provider=None, abstention=rag.FULL_ABSTENTION, admin=None):
    dataset, settings, admin = _example_with_lecture(), _settings(), admin or EvalAdmin()
    lectures = await runner.resolve_lectures(admin, dataset, settings)
    experiment = config_module.capture(name="unit", mode=mode, settings=settings, overrides={}, dataset=dataset,
                                       abstention=abstention, ks=[1, 3], tolerance_seconds=30.0, lectures=list(lectures.values()))
    store = RunStore.create(tmp_path, experiment.run_id)
    store.write_config(experiment.model_dump(mode="json"))
    records = await runner.run(dataset, lectures, store, mode=mode, admin=admin, embedder=Embedder(),
                               provider=provider, settings=settings, abstention=abstention)
    return dataset, store, records, admin


async def test_retrieval_run_stores_ranked_candidates_and_scores_them(tmp_path):
    dataset, store, records, admin = await _run(tmp_path, "retrieval")
    assert admin.writes == [] and all(call[0] == "match_lecture_chunks" for call in admin.rpc_calls)
    first = records[0]
    assert [c["chunk_id"] for c in first["candidates"]] == ["c2", "c0", "c7"]
    assert first["candidates"][0]["start_seconds"] == 115.0 and first["evidence_chunk_ids"] == ["c0", "c2"]
    summary = runner.score(store, dataset)
    assert summary["example_data"] is True
    # Gold span 120-165 (fixture): c2 overlaps at rank 1.
    assert summary["retrieval_candidates"]["n"] == 1 and summary["retrieval_candidates"]["hit@1"] == 1.0
    assert summary["retrieval_candidates"]["mrr"] == 1.0
    assert summary["abstention_threshold_stage_only"]["n_unanswerable"] == 1
    assert (store.directory / "summary.json").exists() and len(store.results()) == 2


async def test_answer_run_reuses_production_rag_and_keeps_provenance(tmp_path):
    dataset, store, records, admin = await _run(tmp_path, "answer", provider=Provider())
    answered = records[0]
    assert answered["outcome"] == "answered" and answered["answer"] == "It updates the parameters."
    assert [s["chunk_id"] for s in answered["sources"] if s["cited"]] == ["c2"]
    assert set(answered["latency"]) == {"embed_ms", "search_ms", "retrieval_ms", "llm_ms", "total_ms"}
    summary = runner.score(store, dataset)
    assert summary["citation_coverage"]["citation_coverage"] == 1.0
    assert summary["citation_support_human"]["support_full"] is None  # no labels -> no number
    assert summary["correctness_human"]["n_labelled"] == 0


async def test_abstention_stage_ablation_changes_behaviour(tmp_path):
    low = [dict(CHUNKS[2])]  # below the 0.6 threshold
    _, _, full, _ = await _run(tmp_path / "full", "answer", provider=Provider(), admin=EvalAdmin(rows=low))
    assert full[0]["outcome"] == "insufficient_evidence" and full[0]["decision"] == "below_threshold"

    class CitesNothing(Provider):
        async def generate_json(self, system, user, *, max_tokens=4096):
            return {"answerable": True, "answer": "Some answer.", "citations": []}

    _, _, no_threshold, _ = await _run(tmp_path / "nothreshold", "answer", provider=CitesNothing(),
                                       abstention=rag.Abstention(use_threshold=False), admin=EvalAdmin(rows=low))
    assert no_threshold[0]["decision"] == "no_valid_citations"  # citation check still declines
    _, _, no_checks, _ = await _run(tmp_path / "nochecks", "answer", provider=CitesNothing(),
                                    abstention=rag.Abstention(use_threshold=False, require_valid_citations=False), admin=EvalAdmin(rows=low))
    assert no_checks[0]["outcome"] == "answered"


async def test_rerun_check_detects_nondeterminism(tmp_path):
    dataset, store, _, admin = await _run(tmp_path, "retrieval")
    same = await runner.rerun_check(store, dataset, admin=admin, embedder=Embedder(), settings=_settings())
    assert same["deterministic"] and same["checked"] == 2
    admin.rows = [CHUNKS[0], CHUNKS[1], CHUNKS[2]]
    changed = await runner.rerun_check(store, dataset, admin=admin, embedder=Embedder(), settings=_settings())
    assert not changed["deterministic"] and changed["mismatches"]


# --- judgments storage and annotation round trip ---------------------------------------------------


async def test_human_labels_round_trip_and_stay_separate_from_llm(tmp_path):
    from evaluation import cli

    dataset, store, records, _ = await _run(tmp_path, "answer", provider=Provider())
    sheet = tmp_path / "labels.csv"
    cli.cmd_template(type("A", (), {"run_dir": str(store.directory), "dataset": str(EXAMPLE), "out": str(sheet)})())
    rows = list(csv.DictReader(sheet.open(encoding="utf-8")))
    rows[0].update(correctness_label="correct", citation_support_label="full", annotator="A1")
    with sheet.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    cli.cmd_import(type("A", (), {"run_dir": str(store.directory), "labels": str(sheet)})())
    store.append_judgments([Judgment(run_id=records[0]["run_id"], question_id="example-q1", kind="correctness", label="incorrect",
                                     judge=JudgeInfo(type="llm", id="judge-model", prompt_version="v1", temperature=0.0))])
    # The dataset used for scoring must be the one with the lecture id filled in.
    summary = runner.score(store, dataset)
    assert summary["correctness_human"]["correct"] == 1.0 and summary["correctness_llm"]["incorrect"] == 1.0
    assert summary["citation_support_human"]["support_full"] == 1.0
    with pytest.raises(ValueError):
        store.append_judgments([Judgment(run_id=records[0]["run_id"], question_id="not-in-run", kind="correctness",
                                         label="correct", judge=JudgeInfo(type="human", id="A1"))])
    with pytest.raises(ValueError):
        Judgment(run_id="r", question_id="q", kind="citation_support", label="mostly", judge=JudgeInfo(type="human", id="A1"))


def test_run_ids_are_never_reused(tmp_path):
    RunStore.create(tmp_path, "run-1")
    with pytest.raises(FileExistsError):
        RunStore.create(tmp_path, "run-1")


def test_judge_must_differ_from_generator():
    same = Settings(_env_file=None, llm_base_url="https://x/v1", llm_model="m", eval_judge_base_url="https://x/v1", eval_judge_model="m")
    with pytest.raises(JudgeConfigError):
        judge_settings(same)
    different = same.model_copy(update={"eval_judge_model": "other"})
    judged = judge_settings(different)
    assert judged.llm_model == "other" and judged.llm_temperature == 0.0
    with pytest.raises(JudgeConfigError):
        judge_settings(Settings(_env_file=None))


def test_literature_template_is_complete_and_unfilled():
    data = json.loads((Path(__file__).resolve().parents[1] / "evaluation" / "literature" / "comparison.json").read_text(encoding="utf-8"))
    labels = set(data["comparability_labels"])
    for entry in data["entries"]:
        assert entry["comparability"] in labels and entry["reason"]
        assert entry["lecturemind_result"] is None  # nothing measured yet
    assert "supervisor" not in json.dumps(data).lower()
