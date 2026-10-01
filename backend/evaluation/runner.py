"""Offline evaluation runner. Reuses app.services.rag; never writes to production tables.

Modes:
  retrieval  embed + match_lecture_chunks + evidence selection (no LLM). Scores retrieval
             and the threshold stage of abstention.
  answer     the full production grounded-answer flow (rag.answer_question), including the
             LLM, abstention stages and citation validation.

Separation from production data: every dataset lecture must be owned by the configured
evaluation account (EVAL_USER_ID), be READY, and have been embedded with the configured
embedding model. Production users' lectures are refused.
"""

import time

from app.core.config import Settings
from app.services import rag
from app.services.llm import LLMError
from evaluation.dataset import EvalDataset
from evaluation.metrics import abstention as abstention_metrics
from evaluation.metrics import judgments as judgment_metrics
from evaluation.metrics import retrieval as retrieval_metrics
from evaluation.metrics.latency import summarize
from evaluation.results import RunStore


class EvaluationSetupError(Exception):
    pass


async def resolve_lectures(admin, dataset: EvalDataset, settings: Settings) -> dict[str, dict]:
    """lecture_key -> {lecture_id, asr, chunking}; enforces the evaluation-account boundary."""
    if not settings.eval_user_id:
        raise EvaluationSetupError("Set EVAL_USER_ID to the dedicated evaluation account before running an evaluation.")
    resolved = {}
    for lecture in dataset.lectures:
        if not lecture.lecture_id:
            raise EvaluationSetupError(f"Lecture '{lecture.lecture_key}' has no lecture_id yet (process it in the evaluation account first).")
        rows = await admin.select("lectures", {"select": "id,user_id,status", "id": f"eq.{lecture.lecture_id}"})
        if not rows:
            raise EvaluationSetupError(f"Lecture '{lecture.lecture_key}' ({lecture.lecture_id}) does not exist.")
        if rows[0]["user_id"] != settings.eval_user_id:
            raise EvaluationSetupError(f"Lecture '{lecture.lecture_key}' is not owned by the evaluation account; refusing to use it.")
        if rows[0]["status"] != "READY":
            raise EvaluationSetupError(f"Lecture '{lecture.lecture_key}' is not READY.")
        chunk = await admin.select(
            "lecture_chunks", {"select": "embedding_model", "lecture_id": f"eq.{lecture.lecture_id}", "limit": "1"}
        )
        if not chunk or chunk[0]["embedding_model"] != settings.embedding_model:
            raise EvaluationSetupError(f"Lecture '{lecture.lecture_key}' was not embedded with {settings.embedding_model}.")
        transcript = await admin.select(
            "transcripts", {"select": "model,model_config,language", "lecture_id": f"eq.{lecture.lecture_id}"}
        )
        runs = await admin.select(
            "processing_jobs", {"select": "id", "lecture_id": f"eq.{lecture.lecture_id}"}
        )
        chunking = None
        if runs:
            stage = await admin.select(
                "processing_stage_runs",
                {"select": "details", "job_id": f"eq.{runs[0]['id']}", "stage": "eq.CHUNKING", "status": "eq.succeeded",
                 "order": "finished_at.desc", "limit": "1"},
            )
            chunking = (stage[0]["details"] or {}).get("config") if stage else None
        resolved[lecture.lecture_key] = {
            "lecture_key": lecture.lecture_key,
            "lecture_id": lecture.lecture_id,
            "asr": transcript[0] if transcript else None,
            "chunking": chunking,
        }
    return resolved


def _chunk_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": str(row["chunk_id"]),
            "sequence": row["sequence"],
            "start_seconds": float(row["start_seconds"]),
            "end_seconds": float(row["end_seconds"]),
            "similarity": float(row["similarity"]),
        }
        for row in rows
    ]


async def evaluate_question(question, lecture_id: str, *, mode, admin, embedder, provider, settings, abstention) -> dict:
    captured: list[dict] = []

    async def retrieve(vector: str, count: int) -> list[dict]:
        rows = await admin.rpc(
            "match_lecture_chunks", {"p_lecture_id": lecture_id, "p_query_embedding": vector, "p_match_count": count}
        )
        captured.extend(rows)
        return rows

    started = time.monotonic()
    record = {"question_id": question.question_id, "lecture_key": question.lecture_key, "lecture_id": lecture_id,
              "answerable": question.answerable}
    if mode == "retrieval":
        fetched = await rag.retrieve_candidates(question.question, retrieve, embedder, settings.rag_top_k)
        min_similarity = settings.rag_min_similarity if abstention.use_threshold else float("-inf")
        evidence = rag.select_evidence(fetched.candidates, min_similarity, settings.rag_context_tokens)
        record.update(
            outcome=None,
            threshold_decision="evidence" if evidence else "below_threshold",
            evidence_chunk_ids=[p.chunk_id for p in evidence],
            latency={"embed_ms": fetched.embed_ms, "search_ms": fetched.search_ms,
                     "retrieval_ms": fetched.embed_ms + fetched.search_ms, "llm_ms": None,
                     "total_ms": int((time.monotonic() - started) * 1000)},
        )
    else:
        try:
            result = await rag.answer_question(
                question=question.question, lecture={"title": question.lecture_key}, retrieve=retrieve,
                embedder=embedder, provider=provider, settings=settings, abstention=abstention,
            )
        except LLMError as error:
            record.update(outcome="error", error_code=error.code, latency={"total_ms": int((time.monotonic() - started) * 1000)})
        else:
            record.update(
                outcome=result.outcome,
                decision=result.retrieval.get("decision"),
                answer=result.answer,
                sources=result.sources,
                evidence_chunk_ids=result.retrieval.get("used_chunk_ids", []),
                latency={"embed_ms": result.retrieval.get("embed_ms"), "search_ms": result.retrieval.get("search_ms"),
                         "retrieval_ms": result.retrieval_ms, "llm_ms": result.llm_ms, "total_ms": result.latency_ms},
            )
    record["candidates"] = _chunk_rows(captured)
    return record


async def run(dataset: EvalDataset, lectures: dict[str, dict], store: RunStore, *, mode, admin, embedder, provider,
              settings, abstention: rag.Abstention) -> list[dict]:
    if mode == "answer" and provider is None:
        raise EvaluationSetupError("Answer mode needs a configured LLM (LLM_BASE_URL/LLM_MODEL).")
    run_id = store.config()["run_id"]
    records = []
    for question in dataset.questions:  # sequential: latency is measured per question, unshared
        record = await evaluate_question(
            question, lectures[question.lecture_key]["lecture_id"], mode=mode, admin=admin, embedder=embedder,
            provider=provider, settings=settings, abstention=abstention,
        )
        record["run_id"] = run_id
        store.append_result(record)
        records.append(record)
    return records


def _spans(question) -> list[retrieval_metrics.Span]:
    return [retrieval_metrics.Span(span.start_seconds, span.end_seconds) for span in question.gold_spans]


def score(store: RunStore, dataset: EvalDataset) -> dict:
    """Aggregates from stored results and judgments (re-computable; nothing is estimated)."""
    config = store.config()
    records = store.results()
    by_id = {q.question_id: q for q in dataset.questions}
    ks, tolerance = config["metrics"]["ks"], config["metrics"]["timestamp_tolerance_seconds"]

    candidate_scores, evidence_scores = [], []
    for record in records:
        question = by_id[record["question_id"]]
        if not question.answerable:
            continue
        ranked = [retrieval_metrics.Retrieved(c["start_seconds"], c["end_seconds"]) for c in record["candidates"]]
        candidate_scores.append(retrieval_metrics.score_question(ranked, _spans(question), ks, tolerance))
        # The passages actually given to the generator (after the threshold and context budget).
        evidence_ids = set(record.get("evidence_chunk_ids") or [])
        evidence = [r for r, c in zip(ranked, record["candidates"]) if c["chunk_id"] in evidence_ids]
        hit = any(retrieval_metrics.is_relevant(chunk, _spans(question), tolerance) for chunk in evidence)
        evidence_scores.append({"evidence_hit": 1.0 if hit else 0.0})

    summary = {
        "run_id": config["run_id"],
        "example_data": config["dataset"]["kind"] == "example",
        "dataset": config["dataset"],
        "config_hash": config["config_hash"],
        "n_questions": len(records),
        "retrieval_candidates": retrieval_metrics.aggregate(candidate_scores),
        "retrieval_evidence_after_threshold": retrieval_metrics.aggregate(evidence_scores),
        "latency_ms": {key: summarize([(r.get("latency") or {}).get(key) for r in records])
                       for key in ("retrieval_ms", "llm_ms", "total_ms")},
    }
    if config["mode"] == "answer":
        scored = [r for r in records if r["outcome"] in (abstention_metrics.ANSWERED, abstention_metrics.REFUSED)]
        summary["errors"] = sum(1 for r in records if r["outcome"] == "error")
        summary["abstention"] = abstention_metrics.abstention(scored)
        summary["citation_coverage"] = abstention_metrics.citation_coverage(scored)
        judgments = store.judgments()
        for judge_type in ("human", "llm"):
            support = {j.question_id: j.label for j in judgments if j.kind == "citation_support" and j.judge.type == judge_type}
            correct = {j.question_id: j.label for j in judgments if j.kind == "correctness" and j.judge.type == judge_type}
            summary[f"citation_support_{judge_type}"] = abstention_metrics.citation_support(scored, support)
            summary[f"correctness_{judge_type}"] = judgment_metrics.correctness(correct)
    else:
        threshold_only = [{"answerable": r["answerable"],
                           "outcome": abstention_metrics.REFUSED if r["threshold_decision"] == "below_threshold" else abstention_metrics.ANSWERED}
                          for r in records]
        summary["abstention_threshold_stage_only"] = abstention_metrics.abstention(threshold_only)
    store.write_summary(summary)
    return summary


async def rerun_check(store: RunStore, dataset: EvalDataset, *, admin, embedder, settings, tolerance: float = 1e-9) -> dict:
    """Repeat retrieval for every question and compare chunk ids, order and similarities with the stored run."""
    stored = {record["question_id"]: record for record in store.results()}
    mismatches = []
    for question in dataset.questions:
        record = stored.get(question.question_id)
        if record is None:
            continue
        rerun = await evaluate_question(
            question, record["lecture_id"], mode="retrieval", admin=admin, embedder=embedder, provider=None,
            settings=settings, abstention=rag.FULL_ABSTENTION,
        )
        before, after = record["candidates"], rerun["candidates"]
        same = [c["chunk_id"] for c in before] == [c["chunk_id"] for c in after] and all(
            abs(a["similarity"] - b["similarity"]) <= tolerance for a, b in zip(before, after)
        )
        if not same:
            mismatches.append(question.question_id)
    return {"checked": len(stored), "mismatches": mismatches, "deterministic": not mismatches, "tolerance": tolerance}

