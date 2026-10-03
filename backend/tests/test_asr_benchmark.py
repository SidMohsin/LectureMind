"""ASR benchmark tooling, with synthetic archives and a fake transcriber (no models, no real data).

The texts below are unit-test fixtures, not dataset content or results.
"""

import io
import json
import tarfile

import pytest

pytest.importorskip("whisper_normalizer")

from app.intelligence.transcription import TranscribedSegment, Transcript  # noqa: E402
from evaluation import asr_benchmark  # noqa: E402


class FakeTranscriber:
    """Returns a fixed hypothesis per file name; raises like FFmpeg does on bad audio."""

    def __init__(self, hypotheses):
        self.hypotheses = hypotheses
        self.calls = []

    def config(self):
        return {"implementation": "fake", "model": "fake", "beam_size": 5, "language": "auto", "vad_filter": True}

    def transcribe(self, audio, progress):
        self.calls.append(audio.stem)
        if audio.read_bytes() == b"this is not audio":
            raise RuntimeError("FFmpeg could not decode the audio")
        text = self.hypotheses[audio.stem]
        return Transcript(
            language="en",
            language_probability=0.99,
            duration_seconds=4.0,
            segments=[TranscribedSegment(0.0, 4.0, f" {text}", None, None)],
            model="fake",
            model_config=self.config(),
        )


def _librispeech_archive(path, references):
    with tarfile.open(path, "w:gz") as tar:

        def add(name, data):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        add("LibriSpeech/README.TXT", b"top-level files, as in the real archives")
        lines = "\n".join(f"{utt} {text}" for utt, text in references.items()) + "\n"
        add("LibriSpeech/test-clean/1/2/1-2.trans.txt", lines.encode())
        for utt in references:
            add(f"LibriSpeech/test-clean/1/2/{utt}.flac", b"fake flac " + utt.encode())
    return path


def test_selection_is_deterministic_midpoints():
    ids = [f"u{i:02d}" for i in range(10)]
    assert asr_benchmark.select(list(reversed(ids)), 2) == ["u02", "u07"]
    assert asr_benchmark.select(ids, 1) == ["u05"]
    assert asr_benchmark.select(ids, None) == ids
    assert asr_benchmark.select(ids, 50) == ids
    with pytest.raises(ValueError):
        asr_benchmark.select(ids, 0)


def test_score_reports_both_normalizers_and_skips_long_cer(monkeypatch):
    lecturemind, whisper = asr_benchmark.normalizers()
    scores = asr_benchmark.score("HELLO WORLD", "hello, word", lecturemind)
    assert scores["wer"]["substitutions"] == 1 and scores["wer"]["reference_length"] == 2
    assert scores["cer"]["reference_length"] == len("helloworld")
    # Whisper's normalizer standardizes spellings ours deliberately does not.
    assert asr_benchmark.score("colour", "color", whisper)["wer"]["errors"] == 0
    assert asr_benchmark.score("colour", "color", lecturemind)["wer"]["errors"] == 1
    monkeypatch.setattr(asr_benchmark, "CER_MAX_CHARS", 3)
    assert asr_benchmark.score("HELLO WORLD", "hello world", lecturemind)["cer"] is None


def test_librispeech_smoke_run_writes_labelled_results_and_survives_errors(tmp_path):
    references = {f"1-2-{i:04d}": text for i, text in enumerate(["A B C", "D E", "F G H", "I J"])}
    archive = _librispeech_archive(tmp_path / "test-clean.tar.gz", references)
    hypotheses = {"1-2-0001": "d e", "1-2-0003": "i x"}
    transcriber = FakeTranscriber(hypotheses)
    workdir = tmp_path / "work"
    workdir.mkdir()

    directory = asr_benchmark.run(
        source="librispeech", dataset_path=archive, out_root=tmp_path / "runs", transcriber=transcriber,
        limit=2, error_probe_item=True, workdir=workdir, log=lambda _: None,
    )  # fmt: skip

    assert directory.parent.name == "smoke"
    config = json.loads((directory / "config.json").read_text())
    assert config["purpose"] == "smoke" and config["label"] == asr_benchmark.SMOKE_LABEL
    assert config["dataset"]["subset"] == "test-clean" and config["dataset"]["n_available"] == 4
    assert config["dataset"]["selected_ids"] == ["1-2-0001", "1-2-0003"]
    assert config["dataset"]["file_sha256"] and config["git"].keys() >= {"commit", "dirty"}
    assert [n["id"] for n in config["normalizers"]] == ["lecturemind", "whisper_english"]
    assert config["asr"]["random_seed"] == 0 and config["config_hash"]

    records = [json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()]
    assert [r["id"] for r in records] == ["1-2-0001", "1-2-0003", asr_benchmark.PROBE_ID]
    assert records[0]["reference"] == "D E" and records[0]["hypothesis"] == "d e"
    assert records[2]["status"] == "error" and records[2]["error_type"] == "RuntimeError"

    summary = json.loads((directory / "summary.json").read_text())
    assert summary["label"] == asr_benchmark.SMOKE_LABEL
    assert summary["items_scored"] == 2 and summary["items_failed"] == 0
    assert summary["probes"] == [{"id": asr_benchmark.PROBE_ID, "status": "error", "error_type": "RuntimeError"}]
    corpus = summary["corpus"]["lecturemind"]["wer"]
    assert (corpus["errors"], corpus["reference_length"]) == (1, 4)  # the probe is excluded
    assert summary["audio_seconds"] == 8.0


def test_benchmark_purpose_refuses_subsets_and_probes(tmp_path):
    archive = _librispeech_archive(tmp_path / "a.tar.gz", {"1-2-0000": "A"})
    common = dict(source="librispeech", dataset_path=archive, out_root=tmp_path, transcriber=FakeTranscriber({}), workdir=tmp_path)
    with pytest.raises(ValueError):
        asr_benchmark.run(purpose="benchmark", limit=1, **common)
    with pytest.raises(ValueError):
        asr_benchmark.run(purpose="benchmark", error_probe_item=True, **common)
    with pytest.raises(ValueError):
        asr_benchmark.run(purpose="smoke", **common)


def test_tedlium_parquet_source(tmp_path):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    table = pa.table({
        "audio": [{"bytes": b"wav-" + name.encode(), "path": f"{name}-merged.wav"} for name in ("TalkB", "TalkA", "TalkC")],
        "text": [" b words", " a words", " c words"],
        "speaker_id": ["TalkB", "TalkA", "TalkC"],
    })  # fmt: skip
    path = tmp_path / "test.parquet"
    pq.write_table(table, path)
    workdir = tmp_path / "work"
    workdir.mkdir()
    items, meta = asr_benchmark.tedlium_items(path, workdir, limit=1)
    assert [item.id for item in items] == ["TalkB"] and items[0].reference == "b words"
    assert items[0].audio.read_bytes() == b"wav-TalkB"
    assert meta["n_available"] == 3 and meta["license"] == "CC BY-NC-ND 3.0"


def test_compare_detects_differences(tmp_path):
    for name, hypothesis in (("a", "x y"), ("b", "x y"), ("c", "x z")):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "config.json").write_text(json.dumps({"config_hash": "h"}))
        (directory / "results.jsonl").write_text(json.dumps({"id": "u1", "status": "ok", "hypothesis": hypothesis}) + "\n")
    assert asr_benchmark.compare(tmp_path / "a", tmp_path / "b")["identical"] is True
    result = asr_benchmark.compare(tmp_path / "a", tmp_path / "c")
    assert result["identical"] is False and result["differing_items"] == ["u1"]
