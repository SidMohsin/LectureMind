"""Versioned evaluation dataset format.

One JSON file per dataset version. Each question belongs to one lecture of the dataset,
is answerable (with >= 1 gold supporting span and a reference answer) or deliberately
unanswerable (no spans), and carries annotation provenance.

Research rules enforced here:
* `split` is "calibration", "dev" or "test". Calibration/dev data may be used for tuning
  (thresholds, top-K...). Test data may only be run when the file is `frozen`, and the
  runner refuses parameter sweeps on it (tune on calibration, then run the test once).
* The content hash (canonical JSON of the questions and lectures) identifies the exact
  dataset used by a run; results record it.
* `kind: "example"` files exist only to document the format and test the tooling.
  Anything computed from them is labelled EXAMPLE and is not a research result.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "lecturemind-eval-dataset/v1"


class GoldSpan(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    note: str | None = None

    @model_validator(mode="after")
    def _ordered(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError("A gold span must end after it starts.")
        return self


class Agreement(BaseModel):
    """Inter-annotator agreement for this item or dataset (e.g. Cohen's kappa on a double-annotated subset)."""

    metric: str
    value: float
    n: int = Field(ge=1)
    annotators: list[str] = []


class Annotation(BaseModel):
    annotators: list[str] = Field(min_length=1)
    guideline_version: str
    created_at: datetime
    reviewed_by: list[str] = []
    agreement: Agreement | None = None
    notes: str | None = None


class EvalLecture(BaseModel):
    lecture_key: str = Field(min_length=1)
    # The lecture as processed in the evaluation account (set once it has been ingested).
    lecture_id: str | None = None
    title: str
    source: str  # e.g. a URL or "own recording", with licence/rights notes where relevant
    duration_seconds: float | None = None
    reference_transcript: str | None = None  # path to a human reference transcript, if any


class EvalQuestion(BaseModel):
    question_id: str = Field(min_length=1)
    lecture_key: str
    question: str = Field(min_length=3)
    answerable: bool
    gold_spans: list[GoldSpan] = []
    reference_answer: str | None = None
    difficulty: Literal["easy", "medium", "hard"] | None = None
    question_type: str | None = None  # e.g. definition, explanation, logistics, off_topic, related_but_absent
    source: str  # how the question was written, e.g. "human-written by annotator A1"
    annotation: Annotation

    @model_validator(mode="after")
    def _consistent(self):
        if self.answerable and (not self.gold_spans or not (self.reference_answer or "").strip()):
            raise ValueError(f"{self.question_id}: answerable questions need gold spans and a reference answer.")
        if not self.answerable and self.gold_spans:
            raise ValueError(f"{self.question_id}: unanswerable questions must not have gold spans.")
        return self


class EvalDataset(BaseModel):
    schema_version: Literal["lecturemind-eval-dataset/v1"] = SCHEMA_VERSION
    dataset_id: str
    version: str
    kind: Literal["research", "example"] = "research"
    split: Literal["calibration", "dev", "test"]
    frozen: bool = False
    frozen_at: datetime | None = None
    description: str
    lectures: list[EvalLecture] = Field(min_length=1)
    questions: list[EvalQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def _integrity(self):
        keys = [lecture.lecture_key for lecture in self.lectures]
        if len(keys) != len(set(keys)):
            raise ValueError("lecture_key values must be unique.")
        ids = [question.question_id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question_id values must be unique.")
        unknown = {q.lecture_key for q in self.questions} - set(keys)
        if unknown:
            raise ValueError(f"Questions refer to unknown lectures: {sorted(unknown)}")
        if self.frozen and self.frozen_at is None:
            raise ValueError("A frozen dataset must record frozen_at.")
        return self

    @property
    def is_example(self) -> bool:
        return self.kind == "example"

    def content_hash(self) -> str:
        payload = {
            "lectures": [lecture.model_dump(mode="json") for lecture in self.lectures],
            "questions": [question.model_dump(mode="json") for question in self.questions],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def lecture(self, key: str) -> EvalLecture:
        return next(lecture for lecture in self.lectures if lecture.lecture_key == key)


def load_dataset(path: str | Path) -> EvalDataset:
    return EvalDataset.model_validate_json(Path(path).read_text(encoding="utf-8"))


class DatasetPolicyError(Exception):
    pass


def check_run_policy(dataset: EvalDataset, *, sweep: bool) -> None:
    """Calibration and test data stay separate: tuning only on calibration/dev, test only when frozen."""
    if dataset.split == "test" and not dataset.frozen:
        raise DatasetPolicyError("Test data can only be evaluated once the dataset is frozen (frozen: true, frozen_at set).")
    if dataset.split == "test" and sweep:
        raise DatasetPolicyError("Parameter sweeps are not allowed on test data. Tune on a calibration/dev split.")
