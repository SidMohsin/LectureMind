"""ASR benchmark: WER/CER of the production transcriber on public test sets.

Sources (read in place, never modified or committed):
  - LibriSpeech test-clean / test-other (OpenSLR SLR12, CC BY 4.0): the original .tar.gz,
    with <id>.flac audio and per-chapter .trans.txt references.
  - TED-LIUM 3 legacy test (CC BY-NC-ND 3.0), as the "distil-whisper/tedlium-long-form"
    test parquet: one row per talk (merged 16 kHz WAV + merged reference text).

Audio goes through app.intelligence.transcription.FasterWhisperTranscriber, i.e. the same
FFmpeg decode, model, beam size, language detection and VAD settings as lecture processing;
nothing is tuned here. The hypothesis is the transcriber's segment texts joined by spaces.

Every utterance is scored with two normalizers, reported separately:
  - "lecturemind-wer-normalizer/v1" (evaluation.metrics.wer), the project normalizer;
  - Whisper's English normalizer (whisper-normalizer package, a port of
    openai/whisper EnglishTextNormalizer), so results can be placed next to papers that
    use it. Comparability still depends on dataset preparation and model size.
Corpus WER/CER sum edits and reference lengths over items (not a mean of item rates).

Selection is deterministic: items are sorted by id and, with a limit, the item at the
midpoint of each of `limit` equal slices of the sorted list is taken
(SELECTION_RULE). The selected ids are stored in the run config.

Runs have a purpose. "smoke" runs are engineering checks on a few items, labelled as such
in every output; their numbers are not results and must not be used to change settings
(these are test splits). "benchmark" runs score the whole split.
"""

import hashlib
import io
import json
import os
import platform
import tarfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from evaluation.config import git_state, package_version, sha256_text
from evaluation.metrics import wer as wer_metrics

BENCHMARK_VERSION = "asr-benchmark/v1"
SELECTION_RULE = "sorted-ids-slice-midpoints/v1"
SMOKE_LABEL = "SMOKE TEST - engineering validation only. NOT a research, benchmark or thesis result."
PROBE_ID = "error-probe"
# Character DP is O(n*m) in pure Python; whole TED talks (~20k characters) are skipped for CER.
CER_MAX_CHARS = 5000
PURPOSES = ("smoke", "benchmark")


@dataclass
class Item:
    id: str
    subset: str
    reference: str
    audio: Path
    probe: bool = False


@dataclass
class Normalizer:
    id: str
    version: str
    apply: Callable[[str], str]


def normalizers() -> list[Normalizer]:
    from whisper_normalizer.english import EnglishTextNormalizer

    whisper = EnglishTextNormalizer()
    return [
        Normalizer("lecturemind", wer_metrics.NORMALIZER_VERSION, wer_metrics.normalize),
        Normalizer(
            "whisper_english",
            f"whisper-normalizer/{package_version('whisper-normalizer') or package_version('whisper_normalizer')}",
            whisper,
        ),
    ]


def select(ids: list[str], limit: int | None) -> list[str]:
    ordered = sorted(ids)
    if limit is None or limit >= len(ordered):
        return ordered
    if limit < 1:
        raise ValueError("limit must be at least 1")
    n = len(ordered)
    return [ordered[int((index + 0.5) * n / limit)] for index in range(limit)]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --- Sources --------------------------------------------------------------------------------


def librispeech_items(archive: Path, workdir: Path, limit: int | None) -> tuple[list[Item], dict]:
    """Read references and the selected .flac files from an original LibriSpeech .tar.gz."""
    references: dict[str, str] = {}
    audio_members: dict[str, str] = {}
    subsets = set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if len(parts) >= 3 and parts[0] == "LibriSpeech":  # not top-level README/SPEAKERS files
                subsets.add(parts[1])
            if member.name.endswith(".trans.txt"):
                for line in tar.extractfile(member).read().decode("utf-8").splitlines():
                    if line.strip():
                        utterance, _, text = line.strip().partition(" ")
                        references[utterance] = text
            elif member.name.endswith(".flac"):
                audio_members[Path(member.name).stem] = member.name
    if len(subsets) != 1:
        raise ValueError(f"expected one LibriSpeech subset in {archive.name}, found {sorted(subsets)}")
    missing = sorted(set(audio_members) ^ set(references))
    if missing:
        raise ValueError(f"{len(missing)} utterances lack audio or a reference, e.g. {missing[:3]}")
    chosen = select(list(references), limit)
    wanted = {audio_members[utterance]: utterance for utterance in chosen}
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if member.name in wanted:
                (workdir / f"{wanted[member.name]}.flac").write_bytes(tar.extractfile(member).read())
    subset = subsets.pop()
    items = [Item(utterance, subset, references[utterance], workdir / f"{utterance}.flac") for utterance in chosen]
    return items, {
        "name": "librispeech",
        "subset": subset,
        "license": "CC BY 4.0",
        "source": "https://www.openslr.org/12/",
        "reference_preparation": "as distributed (.trans.txt)",
        "n_available": len(references),
    }


def tedlium_items(parquet: Path, workdir: Path, limit: int | None) -> tuple[list[Item], dict]:
    """Read talks from the distil-whisper/tedlium-long-form test parquet."""
    import pyarrow.parquet as pq

    names = pq.ParquetFile(parquet).schema_arrow.names
    if not {"audio", "text", "speaker_id"} <= set(names):
        raise ValueError(f"unexpected TED-LIUM parquet columns: {names}")
    talks = {row["speaker_id"]: row["text"] for row in pq.read_table(parquet, columns=["speaker_id", "text"]).to_pylist()}
    chosen = select(list(talks), limit)
    table = pq.read_table(parquet, columns=["speaker_id", "audio"])
    for row in table.to_pylist():
        if row["speaker_id"] in chosen:
            (workdir / f"{row['speaker_id']}.wav").write_bytes(row["audio"]["bytes"])
    items = [Item(talk, "test", talks[talk].strip(), workdir / f"{talk}.wav") for talk in chosen]
    return items, {
        "name": "tedlium3-legacy-test",
        "subset": "test",
        "license": "CC BY-NC-ND 3.0",
        "source": "https://huggingface.co/datasets/distil-whisper/tedlium-long-form (built from LIUM/tedlium release3)",
        "reference_preparation": "as distributed (merged talk text; no <unk>, apostrophes joined)",
        "n_available": len(talks),
    }


SOURCES = {"librispeech": librispeech_items, "tedlium": tedlium_items}


def error_probe(workdir: Path) -> Item:
    """A deliberately undecodable file, to check that one failure is recorded and the run continues."""
    path = workdir / f"{PROBE_ID}.flac"
    path.write_bytes(b"this is not audio")
    return Item(PROBE_ID, "probe", "error probe", path, probe=True)


# --- Scoring --------------------------------------------------------------------------------


def score(reference: str, hypothesis: str, normalizer: Normalizer) -> dict:
    ref, hyp = normalizer.apply(reference), normalizer.apply(hypothesis)
    word = wer_metrics.edit_counts(ref.split(), hyp.split())
    ref_chars, hyp_chars = ref.replace(" ", ""), hyp.replace(" ", "")
    char = None
    if max(len(ref_chars), len(hyp_chars)) <= CER_MAX_CHARS:
        char = wer_metrics.edit_counts(list(ref_chars), list(hyp_chars)).as_dict()
    return {"wer": word.as_dict(), "cer": char}


def summarize(records: list[dict], normalizer_ids: list[str]) -> dict:
    scored = [r for r in records if r["status"] == "ok" and not r["probe"]]
    errors = [r for r in records if r["status"] == "error" and not r["probe"]]
    probes = [r for r in records if r["probe"]]
    corpus = {}
    for nid in normalizer_ids:
        totals = {}
        for kind in ("wer", "cer"):
            counted = [r["scores"][nid][kind] for r in scored if r["scores"][nid][kind] is not None]
            edits = sum(c["errors"] for c in counted)
            length = sum(c["reference_length"] for c in counted)
            totals[kind] = {
                "items": len(counted),
                "substitutions": sum(c["substitutions"] for c in counted),
                "deletions": sum(c["deletions"] for c in counted),
                "insertions": sum(c["insertions"] for c in counted),
                "errors": edits,
                "reference_length": length,
                "rate": edits / length if length else None,
            }
        corpus[nid] = totals
    audio = sum(r["audio_seconds"] for r in scored)
    asr = sum(r["asr_seconds"] for r in scored)
    return {
        "items_scored": len(scored),
        "items_failed": len(errors),
        "probes": [{"id": p["id"], "status": p["status"], "error_type": p.get("error_type")} for p in probes],
        "corpus": corpus,
        "audio_seconds": round(audio, 3),
        "asr_seconds": round(asr, 3),
        "real_time_factor": round(asr / audio, 4) if audio else None,
        "languages_detected": sorted({r["language"] for r in scored if r.get("language")}),
    }


# --- Runner ---------------------------------------------------------------------------------


def make_config(*, purpose, source_meta, dataset_path, items, transcriber_config, seed, normalizer_list) -> dict:
    selected = [item for item in items if not item.probe]
    config = {
        "benchmark_version": BENCHMARK_VERSION,
        "run_id": f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}",
        "purpose": purpose,
        "label": SMOKE_LABEL if purpose == "smoke" else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git": git_state(),
        "dataset": {
            **source_meta,
            "file": dataset_path.name,
            "file_sha256": file_sha256(dataset_path),
            "selection_rule": SELECTION_RULE,
            "n_selected": len(selected),
            "selected_ids": [item.id for item in selected],
            "references_sha256": sha256_text(json.dumps({i.id: i.reference for i in selected}, sort_keys=True)),
        },
        "asr": {**transcriber_config, "random_seed": seed, "cpu_threads": "library default"},
        "normalizers": [{"id": n.id, "version": n.version} for n in normalizer_list],
        "scoring": {"cer_max_chars": CER_MAX_CHARS, "corpus_rate": "sum of edits / sum of reference lengths"},
        "software": {
            "faster-whisper": package_version("faster-whisper"),
            "ctranslate2": package_version("ctranslate2"),
            "whisper-normalizer": package_version("whisper-normalizer"),
            "pyarrow": package_version("pyarrow"),
            "python": platform.python_version(),
        },
        "machine": {"platform": platform.platform(), "processor": platform.processor(), "cpu_count": os.cpu_count()},
    }
    hashed = {key: config[key] for key in ("benchmark_version", "asr", "normalizers", "scoring")}
    hashed["dataset"] = {k: config["dataset"][k] for k in ("file_sha256", "selection_rule", "selected_ids", "references_sha256")}
    config["config_hash"] = sha256_text(json.dumps(hashed, sort_keys=True))
    return config


def transcribe_item(item: Item, transcriber, normalizer_list, seed: int) -> dict:
    from app.intelligence.transcription import TranscriptionProgress

    record = {"id": item.id, "subset": item.subset, "probe": item.probe, "reference": item.reference}
    try:
        import ctranslate2

        ctranslate2.set_random_seed(seed)  # per item, so results don't depend on run order
    except (ImportError, AttributeError):
        pass
    started = time.perf_counter()
    try:
        transcript = transcriber.transcribe(item.audio, TranscriptionProgress())
    except Exception as exc:  # recorded, never fatal for the run
        record.update(
            status="error",
            error_type=type(exc).__name__,
            error=str(exc)[:300],
            asr_seconds=round(time.perf_counter() - started, 3),
        )
        return record
    elapsed = time.perf_counter() - started
    hypothesis = " ".join(segment.text.strip() for segment in transcript.segments).strip()
    record.update(
        status="ok",
        hypothesis=hypothesis,
        audio_seconds=round(transcript.duration_seconds, 3),
        asr_seconds=round(elapsed, 3),
        real_time_factor=round(elapsed / transcript.duration_seconds, 4) if transcript.duration_seconds else None,
        language=transcript.language,
        language_probability=transcript.language_probability,
        segments=len(transcript.segments),
        scores={n.id: score(item.reference, hypothesis, n) for n in normalizer_list},
    )
    return record


def run(
    *,
    source: str,
    dataset_path: Path,
    out_root: Path,
    transcriber,
    purpose: str = "smoke",
    limit: int | None = None,
    error_probe_item: bool = False,
    seed: int = 0,
    workdir: Path,
    log: Callable[[str], None] = print,
) -> Path:
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of {PURPOSES}")
    if purpose == "benchmark" and (limit is not None or error_probe_item):
        raise ValueError("a benchmark run scores the whole split: --limit and --error-probe are for smoke runs only")
    if purpose == "smoke" and limit is None:
        raise ValueError("a smoke run needs --limit")
    items, meta = SOURCES[source](dataset_path, workdir, limit)
    if error_probe_item:
        items.append(error_probe(workdir))
    normalizer_list = normalizers()

    load_started = time.perf_counter()
    if hasattr(transcriber, "_model"):
        transcriber._model()  # load (or fetch from cache) before timing items
    model_load_seconds = time.perf_counter() - load_started

    config = make_config(
        purpose=purpose,
        source_meta=meta,
        dataset_path=dataset_path,
        items=items,
        transcriber_config=transcriber.config(),
        seed=seed,
        normalizer_list=normalizer_list,
    )
    directory = out_root / ("smoke" if purpose == "smoke" else "benchmark") / config["run_id"]
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    wall_started = time.perf_counter()
    records = []
    with (directory / "results.jsonl").open("w", encoding="utf-8") as results:
        for position, item in enumerate(items, 1):
            record = transcribe_item(item, transcriber, normalizer_list, seed)
            records.append(record)
            results.write(json.dumps(record, ensure_ascii=False) + "\n")
            results.flush()
            status = record["status"] if record["status"] == "error" else f"{record['audio_seconds']:.1f}s audio"
            log(f"[{position}/{len(items)}] {item.id}: {status} in {record['asr_seconds']:.1f}s")
    summary = {
        "run_id": config["run_id"],
        "purpose": purpose,
        "label": config["label"],
        "config_hash": config["config_hash"],
        **summarize(records, [n.id for n in normalizer_list]),
        "model_load_seconds": round(model_load_seconds, 3),
        "wall_seconds": round(time.perf_counter() - wall_started, 3),
    }
    (directory / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return directory


def compare(run_a: Path, run_b: Path) -> dict:
    """Determinism check: same configuration hash and identical hypotheses per item."""

    def load(directory):
        config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
        lines = (directory / "results.jsonl").read_text(encoding="utf-8").splitlines()
        return config, {r["id"]: r for r in (json.loads(line) for line in lines if line.strip())}

    config_a, a = load(run_a)
    config_b, b = load(run_b)
    differing = sorted(
        item for item in set(a) | set(b)
        if (a.get(item) or {}).get("hypothesis") != (b.get(item) or {}).get("hypothesis")
        or (a.get(item) or {}).get("status") != (b.get(item) or {}).get("status")
    )  # fmt: skip
    return {
        "same_config_hash": config_a["config_hash"] == config_b["config_hash"],
        "items_compared": len(set(a) | set(b)),
        "identical": not differing and config_a["config_hash"] == config_b["config_hash"],
        "differing_items": differing,
    }
