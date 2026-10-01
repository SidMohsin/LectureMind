"""Versioned experiment configuration: everything needed to reproduce a run.

A run's configuration is captured from the live application settings (the same values
production uses), plus any explicit overrides for the experiment, plus provenance:
git commit (and whether the working tree had uncommitted changes), prompt hashes, the
dataset version/hash, and the ASR/chunking configuration actually used when each
evaluation lecture was processed (read from its stored transcript metadata, because ASR
and chunking happened at processing time, not at evaluation time).

`config_hash` covers the experimental settings only (not run id, time or git), so two runs
with the same hash used the same configuration.
"""

import hashlib
import json
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from pydantic import BaseModel

from app.core.config import Settings
from app.services import rag

REPO_ROOT = Path(__file__).resolve().parents[2]

# Settings an experiment may override (CLI --set key=value). Anything else is refused,
# so an experiment can't silently change unrelated behaviour.
OVERRIDABLE = {
    "rag_top_k": int,
    "rag_min_similarity": float,
    "rag_context_tokens": int,
    "rag_max_output_tokens": int,
    "llm_temperature": float,
    "llm_model": str,
    "llm_reasoning_effort": str,
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_state(root: Path = REPO_ROOT) -> dict:
    def run(*args):
        try:
            return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"commit": commit, "dirty": bool(status) if status is not None else None}


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def apply_overrides(settings: Settings, overrides: dict[str, str]) -> tuple[Settings, dict]:
    parsed = {}
    for key, raw in overrides.items():
        if key not in OVERRIDABLE:
            raise ValueError(f"'{key}' can't be overridden in an experiment. Allowed: {sorted(OVERRIDABLE)}")
        parsed[key] = OVERRIDABLE[key](raw)
    return settings.model_copy(update=parsed), parsed


class ExperimentConfig(BaseModel):
    run_id: str
    name: str
    created_at: str
    mode: str  # "retrieval" (no LLM) or "answer" (full grounded Q&A)
    git: dict
    dataset: dict
    overrides: dict
    retrieval: dict
    abstention: dict
    embedding: dict
    generator: dict | None
    judge: dict | None = None
    metrics: dict
    lectures: list[dict] = []  # per lecture: id, ASR model/config and chunking actually used
    software: dict
    config_hash: str = ""

    def compute_hash(self) -> str:
        experimental = self.model_dump(
            mode="json", exclude={"run_id", "name", "created_at", "git", "config_hash", "software", "judge"}
        )
        return sha256_text(json.dumps(experimental, sort_keys=True, ensure_ascii=False))


def capture(
    *,
    name: str,
    mode: str,
    settings: Settings,
    overrides: dict,
    dataset,
    abstention: rag.Abstention,
    ks: list[int],
    tolerance_seconds: float,
    lectures: list[dict],
) -> ExperimentConfig:
    from evaluation.metrics.retrieval import METRICS_VERSION

    generator = None
    if mode == "answer":
        generator = {
            "provider_base_url_host": settings.llm_base_url.split("//")[-1].split("/")[0] or None,
            "model": settings.llm_model,
            "temperature": settings.llm_temperature,
            "max_output_tokens": settings.rag_max_output_tokens,
            "reasoning_effort": settings.llm_reasoning_effort or None,
            "prompt_version": rag.PROMPT_VERSION,
            "system_prompt_sha256": sha256_text(rag.SYSTEM),
        }
    config = ExperimentConfig(
        run_id=f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}",
        name=name,
        created_at=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        git=git_state(),
        dataset={
            "dataset_id": dataset.dataset_id,
            "version": dataset.version,
            "split": dataset.split,
            "kind": dataset.kind,
            "frozen": dataset.frozen,
            "content_sha256": dataset.content_hash(),
            "n_questions": len(dataset.questions),
        },
        overrides=overrides,
        retrieval={
            "top_k": settings.rag_top_k,
            "min_similarity": settings.rag_min_similarity,
            "context_tokens": settings.rag_context_tokens,
            "function": "match_lecture_chunks",
        },
        abstention={
            "use_threshold": abstention.use_threshold,
            "use_model_answerable": abstention.use_model_answerable,
            "require_valid_citations": abstention.require_valid_citations,
        },
        embedding={"model": settings.embedding_model, "dimension": settings.embedding_dimension},
        generator=generator,
        metrics={"retrieval_metrics_version": METRICS_VERSION, "ks": ks, "timestamp_tolerance_seconds": tolerance_seconds},
        lectures=lectures,
        software={
            "fastembed": package_version("fastembed"),
            "faster-whisper": package_version("faster-whisper"),
            "ctranslate2": package_version("ctranslate2"),
            "python": platform.python_version(),
        },
    )
    config.config_hash = config.compute_hash()
    return config
