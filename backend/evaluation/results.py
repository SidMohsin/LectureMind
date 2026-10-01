"""Run result storage, kept apart from production data.

Each run is a directory (default backend/evaluation/runs/, git-ignored) containing:

  config.json      the ExperimentConfig (provenance + configuration + hashes)
  results.jsonl    one record per question (retrieved chunks with times and scores,
                   generated answer, outcome, sources, latency)
  judgments.jsonl  appended labels: human annotations (authoritative) and LLM-judge
                   outputs (secondary), each with its judge provenance
  summary.json     aggregates computed from the files above (re-computable at any time)

Nothing is written to Supabase tables; production chat history is never touched.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from evaluation.metrics.abstention import SUPPORT_LABELS
from evaluation.metrics.judgments import CORRECTNESS_LABELS

DEFAULT_RUNS_DIR = Path(__file__).resolve().parent / "runs"


class JudgeInfo(BaseModel):
    type: Literal["human", "llm"]
    id: str  # annotator id, or the judge model name
    provider: str | None = None
    prompt_version: str | None = None
    prompt_sha256: str | None = None
    temperature: float | None = None


class Judgment(BaseModel):
    run_id: str
    question_id: str
    kind: Literal["correctness", "citation_support"]
    label: str
    score: float | None = None
    rationale: str | None = None
    judge: JudgeInfo
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def _label_known(self):
        allowed = CORRECTNESS_LABELS if self.kind == "correctness" else SUPPORT_LABELS
        if self.label not in allowed:
            raise ValueError(f"{self.kind} label must be one of {allowed}, got {self.label!r}")
        return self


class RunStore:
    def __init__(self, directory: Path):
        self.directory = directory

    @classmethod
    def create(cls, root: Path, run_id: str) -> "RunStore":
        directory = root / run_id
        directory.mkdir(parents=True, exist_ok=False)  # a run id is never reused
        return cls(directory)

    def _write_json(self, name: str, data) -> None:
        (self.directory / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def _read_jsonl(self, name: str) -> list[dict]:
        path = self.directory / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def write_config(self, config: dict) -> None:
        self._write_json("config.json", config)

    def config(self) -> dict:
        return json.loads((self.directory / "config.json").read_text(encoding="utf-8"))

    def append_result(self, record: dict) -> None:
        with (self.directory / "results.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def results(self) -> list[dict]:
        return self._read_jsonl("results.jsonl")

    def append_judgments(self, judgments: list[Judgment]) -> None:
        run_id = self.config()["run_id"]
        known = {record["question_id"] for record in self.results()}
        with (self.directory / "judgments.jsonl").open("a", encoding="utf-8") as handle:
            for judgment in judgments:
                if judgment.run_id != run_id:
                    raise ValueError(f"Judgment for run {judgment.run_id} can't be stored in run {run_id}.")
                if judgment.question_id not in known:
                    raise ValueError(f"Judgment for unknown question {judgment.question_id}.")
                handle.write(judgment.model_dump_json() + "\n")

    def judgments(self) -> list[Judgment]:
        return [Judgment.model_validate(item) for item in self._read_jsonl("judgments.jsonl")]

    def write_summary(self, summary: dict) -> None:
        self._write_json("summary.json", summary)
