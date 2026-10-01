"""Phase 5 stages and grounded intelligence generation (fake models, fake LLM, in-memory Supabase)."""

import json
import uuid
from pathlib import Path

import pytest

from app.core.config import Settings
from app.intelligence.generation import ChunkRef, generate, validate, windows, GenerationReport
from app.intelligence.transcription import TranscribedSegment, Transcript
from app.services.llm import LLMError, LLMUsage
from app.workers import intelligence_stages as stages
from app.workers.context import AudioArtifact, JobContext
from app.workers.lifecycle import ProcessingError

from .fakes import FakeAdmin

pytestmark = pytest.mark.anyio

USER = str(uuid.uuid4())


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        supabase_url="https://x.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service",
        work_dir=str(tmp_path),
        llm_base_url="https://llm.example/v1",
        llm_model="test-model",
    )


@pytest.fixture
def admin():
    return FakeAdmin()


async def make_ctx(admin, settings, tmp_path):
    lecture = await admin.insert("lectures", {"user_id": USER, "title": "L", "source_type": "audio", "status": "TRANSCRIBING"})
    job = await admin.insert("processing_jobs", {"lecture_id": lecture["id"], "user_id": USER})
    await admin.rpc("claim_processing_job", {"p_job_id": job["id"], "p_worker": "w", "p_lease_seconds": 60})
    job = admin.rows("processing_jobs", id=job["id"])[0]
    return JobContext(admin, settings, "w", job, lecture, tmp_path)


LECTURE_SENTENCES = [
    "Welcome to machine learning.",
    "Today we cover supervised learning, where each training example has a label.",
    "Linear regression predicts a continuous value from the input features.",
    "The cost function measures the squared error between predictions and labels.",
    "Gradient descent minimizes the cost function by stepping against the gradient.",
    "The learning rate controls the size of each step.",
    "For example, predicting house prices from the size of the house is a regression problem.",
    "Classification instead predicts a discrete label, like spam or not spam.",
]


async def seed_segments(admin, ctx, repeat=6):
    index = 0
    for round_ in range(repeat):
        for sentence in LECTURE_SENTENCES:
            await admin.insert(
                "transcript_segments",
                {
                    "lecture_id": ctx.lecture["id"], "sequence": index, "start_seconds": index * 4.0,
                    "end_seconds": index * 4.0 + 3.8, "raw_text": f" {sentence.lower()} ", "text": None,
                    "avg_logprob": -0.2, "no_speech_prob": 0.01,
                },
            )
            index += 1
    return index


# --- transcription stage ----------------------------------------------------------------------


class FakeTranscriber:
    segments: list = []

    def __init__(self, settings):
        pass

    def transcribe(self, audio, progress):
        progress.processed_seconds = 30.0
        return Transcript(
            language="en", language_probability=0.99, duration_seconds=30.0, segments=list(FakeTranscriber.segments),
            model="faster-whisper/test", model_config={"implementation": "faster-whisper", "model": "test"},
        )


@pytest.fixture
def fake_audio(monkeypatch, tmp_path):
    audio = tmp_path / "audio.flac"
    audio.write_bytes(b"fLaC")

    async def prepare(ctx):
        return AudioArtifact(audio, 30.0, "0" * 64, None, {}, None, None)

    monkeypatch.setattr(stages, "prepare_audio", prepare)
    monkeypatch.setattr(stages, "FasterWhisperTranscriber", FakeTranscriber)


async def test_transcription_persists_ordered_timestamped_segments_and_metadata(admin, settings, tmp_path, fake_audio):
    FakeTranscriber.segments = [
        TranscribedSegment(0.0, 4.2, " Welcome to machine learning.", -0.1, 0.01),
        TranscribedSegment(4.2, 9.8, " Today we cover supervised learning.", -0.2, 0.02),
    ]
    ctx = await make_ctx(admin, settings, tmp_path)
    details = await stages.transcribe(ctx)

    rows = admin.rows("transcript_segments", lecture_id=ctx.lecture["id"])
    assert [(r["sequence"], r["start_seconds"], r["end_seconds"], r["raw_text"]) for r in rows] == [
        (0, 0.0, 4.2, "Welcome to machine learning."),
        (1, 4.2, 9.8, "Today we cover supervised learning."),
    ]
    transcript = admin.rows("transcripts", lecture_id=ctx.lecture["id"])[0]
    assert transcript["segment_count"] == 2 and transcript["model"] == "faster-whisper/test" and transcript["language"] == "en"
    assert details["segments"] == 2 and details["real_time_factor"] is not None

    # Re-running replaces the transcript rather than duplicating it.
    await stages.transcribe(ctx)
    assert len(admin.rows("transcript_segments", lecture_id=ctx.lecture["id"])) == 2
    assert len(admin.rows("transcripts", lecture_id=ctx.lecture["id"])) == 1


async def test_silent_audio_fails_with_a_clear_reason(admin, settings, tmp_path, fake_audio):
    FakeTranscriber.segments = []
    ctx = await make_ctx(admin, settings, tmp_path)
    with pytest.raises(ProcessingError) as caught:
        await stages.transcribe(ctx)
    assert caught.value.code == "no_speech_detected" and not caught.value.retryable


# --- cleaning + chunking + embedding stages ------------------------------------------------------


async def test_cleaning_keeps_raw_text_and_timing(admin, settings, tmp_path):
    ctx = await make_ctx(admin, settings, tmp_path)
    total = await seed_segments(admin, ctx, repeat=1)
    await stages.clean(ctx)
    rows = sorted(admin.rows("transcript_segments", lecture_id=ctx.lecture["id"]), key=lambda r: r["sequence"])
    assert len(rows) == total
    assert rows[0]["raw_text"] == " welcome to machine learning. " and rows[0]["text"] == "Welcome to machine learning."
    assert [r["start_seconds"] for r in rows] == [i * 4.0 for i in range(total)]


async def test_chunking_persists_timestamped_chunks_and_replaces_on_rerun(admin, settings, tmp_path):
    ctx = await make_ctx(admin, settings, tmp_path)
    await seed_segments(admin, ctx)
    await stages.clean(ctx)
    details = await stages.chunk(ctx)

    chunks = sorted(admin.rows("lecture_chunks", lecture_id=ctx.lecture["id"]), key=lambda c: c["sequence"])
    assert details["chunks"] == len(chunks) >= 2
    segments = {r["sequence"]: r for r in admin.rows("transcript_segments", lecture_id=ctx.lecture["id"])}
    for chunk in chunks:
        assert chunk["start_seconds"] == segments[chunk["first_segment"]]["start_seconds"]
        assert chunk["end_seconds"] == segments[chunk["last_segment"]]["end_seconds"]
        assert chunk["embedding"] is None
    await stages.chunk(ctx)
    assert len(admin.rows("lecture_chunks", lecture_id=ctx.lecture["id"])) == len(chunks)


class FakeEmbedder:
    name = "BAAI/bge-small-en-v1.5"
    dimension = 384

    def __init__(self, settings):
        pass

    def embed_passages(self, texts):
        return [[float(len(t) % 7)] + [0.01] * 383 for t in texts]


async def test_every_chunk_gets_an_embedding_with_its_model(admin, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(stages, "FastEmbedEmbedder", FakeEmbedder)
    ctx = await make_ctx(admin, settings, tmp_path)
    await seed_segments(admin, ctx)
    await stages.clean(ctx)
    await stages.chunk(ctx)
    details = await stages.embed(ctx)

    chunks = admin.rows("lecture_chunks", lecture_id=ctx.lecture["id"])
    assert details == {**details, "dimension": 384, "chunks": len(chunks)}
    for chunk in chunks:
        assert chunk["embedding_model"] == "BAAI/bge-small-en-v1.5"
        assert chunk["embedding"].startswith("[") and chunk["embedding"].count(",") == 383
    assert len(chunks) == len({c["sequence"] for c in chunks})  # upsert, not duplicate


# --- grounded generation -----------------------------------------------------------------------


def chunk_refs(n=6):
    return [ChunkRef(i, i * 60.0, i * 60.0 + 58.0, LECTURE_SENTENCES[i % len(LECTURE_SENTENCES)]) for i in range(n)]


GOOD = {
    "summary": "The lecture introduces supervised learning and linear regression, then explains gradient descent.",
    "chapters": [
        {"title": "Supervised learning", "description": "Labels.", "start_chunk": 0, "end_chunk": 2},
        {"title": "Optimization", "description": "Gradient descent.", "start_chunk": 3, "end_chunk": 5},
    ],
    "topics": [{"name": "Regression", "subtopics": ["Linear regression"], "chunks": [2]}],
    "key_concepts": [{"name": "Gradient descent", "explanation": "Steps against the gradient.", "chunks": [4]}],
    "definitions": [{"term": "cost function", "definition": "Squared error between predictions and labels.", "chunks": [3]}],
    "keywords": ["learning rate", "gradient descent"],
    "important_points": [{"point": "The learning rate controls step size.", "chunks": [5]}],
    "examples": [{"description": "Predicting house prices from size.", "chunks": [6]}],
}


def test_grounding_rules_are_enforced_in_code():
    raw = json.loads(json.dumps(GOOD))
    raw["key_concepts"].append({"name": "Transformers", "explanation": "Invented.", "chunks": [99]})  # no valid source
    raw["definitions"].append({"term": "backpropagation", "definition": "Not in lecture.", "chunks": [1]})  # term not said
    raw["keywords"].append("neural network")  # never said
    report = GenerationReport()
    result = validate(raw, chunk_refs(6), report)

    assert [c["name"] for c in result["key_concepts"]] == ["Gradient descent"]
    assert [d["term"] for d in result["definitions"]] == ["cost function"]
    assert result["keywords"] == ["learning rate", "gradient descent"]
    assert result["examples"] == []  # cited chunk 6 doesn't exist in a 6-chunk lecture
    assert report.dropped_items == {"key_concepts": 1, "definitions": 1, "keywords": 1, "examples": 1}


def test_chapters_take_real_chunk_timestamps_and_cover_the_lecture():
    raw = dict(GOOD, chapters=[
        {"title": "Optimization", "start_chunk": 3},
        {"title": "Intro", "start_chunk": 1, "end_chunk": 9},
        {"title": "Bogus", "start_chunk": 42},
    ])
    chapters = validate(raw, chunk_refs(6), GenerationReport())["chapters"]
    assert [(c["title"], c["first_chunk"], c["last_chunk"]) for c in chapters] == [("Intro", 0, 2), ("Optimization", 3, 5)]
    assert chapters[0]["start_seconds"] == 0.0 and chapters[1]["start_seconds"] == 180.0 and chapters[1]["end_seconds"] == 358.0


class FakeProvider:
    name = "llm.example"
    model = "test-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def generate_json(self, system, user, *, max_tokens=4096):
        self.prompts.append((system, user))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


async def test_single_window_lecture_uses_one_call_and_treats_transcript_as_data():
    provider = FakeProvider([GOOD])
    result, report = await generate(provider, chunk_refs(7), window_tokens=100_000)
    system, user = provider.prompts[0]
    assert report.windows == 1 and len(provider.prompts) == 1
    assert "untrusted data" in system and "<transcript>" in user and "[C4 04:00-04:58]" in user
    assert result["summary"].startswith("The lecture")


async def test_long_lecture_is_summarised_in_ordered_parts_then_synthesised():
    chunks = chunk_refs(8)
    parts = windows(chunks, window_tokens=40)
    assert len(parts) > 1
    long_summary = GOOD["summary"] + " Detail about this part of the lecture." * 25
    part_notes = [dict(GOOD, summary=long_summary, chapters=[{"title": f"Part {i}", "start_chunk": p[0].sequence}]) for i, p in enumerate(parts)]
    provider = FakeProvider([*part_notes, GOOD])
    result, report = await generate(provider, chunks, window_tokens=40)

    assert report.windows == len(parts) and len(provider.prompts) == len(parts) + 1
    for index, (_, user) in enumerate(provider.prompts[:-1]):
        assert f"Part {index + 1} of {len(parts)}" in user  # parts are sent in lecture order
    assert "<part_notes>" in provider.prompts[-1][1]
    assert len(result["chapters"]) == 2


async def test_invalid_output_gets_one_repair_attempt():
    provider = FakeProvider([{"summary": "too short"}, GOOD])
    result, _ = await generate(provider, chunk_refs(6), window_tokens=100_000)
    assert len(provider.prompts) == 2 and "previous answer was rejected" in provider.prompts[1][1]
    assert result["chapters"]


async def test_unusable_output_fails_as_retryable():
    provider = FakeProvider([{"summary": "x"}, {"summary": "y"}])
    with pytest.raises(LLMError) as caught:
        await generate(provider, chunk_refs(6), window_tokens=100_000)
    assert caught.value.code == "intelligence_invalid" and caught.value.retryable


# --- intelligence stage ---------------------------------------------------------------------------


async def test_intelligence_stage_persists_grounded_results_with_provenance(admin, settings, tmp_path, monkeypatch):
    provider = FakeProvider([GOOD])
    monkeypatch.setattr(stages, "OpenAICompatibleProvider", lambda http, s: provider)
    provider.usage = LLMUsage(calls=1, prompt_tokens=900, completion_tokens=300, per_call=[{"finish_reason": "stop"}])
    ctx = await make_ctx(admin, settings, tmp_path)
    for c in chunk_refs(6):
        await admin.insert("lecture_chunks", {"lecture_id": ctx.lecture["id"], "sequence": c.sequence, "text": c.text,
                                              "start_seconds": c.start, "end_seconds": c.end, "first_segment": c.sequence,
                                              "last_segment": c.sequence, "token_estimate": 20})
    details = await stages.generate_intelligence(ctx)

    intelligence = admin.rows("lecture_intelligence", lecture_id=ctx.lecture["id"])[0]
    assert intelligence["provider"] == "llm.example" and intelligence["model"] == "test-model"
    assert intelligence["prompt_version"] == "lecture-intelligence/v3"
    assert intelligence["generation"]["prompt_tokens"] == 900
    assert intelligence["key_concepts"][0]["chunks"] == [4]
    chapters = sorted(admin.rows("chapters", lecture_id=ctx.lecture["id"]), key=lambda c: c["sequence"])
    assert [c["title"] for c in chapters] == ["Supervised learning", "Optimization"]
    assert details["counts"]["chapters"] == 2


async def test_missing_llm_configuration_fails_clearly(admin, settings, tmp_path):
    ctx = await make_ctx(admin, settings.model_copy(update={"llm_base_url": ""}), tmp_path)
    with pytest.raises(ProcessingError) as caught:
        await stages.generate_intelligence(ctx)
    assert caught.value.code == "llm_not_configured"


async def test_notes_too_large_for_one_request_are_merged_in_ordered_levels():
    # 24 long chunks -> several parts; each part's notes fit the window but all of them together don't.
    chunks = [ChunkRef(i, i * 60.0, i * 60.0 + 58.0, (LECTURE_SENTENCES[i % 8] + " ") * 8) for i in range(40)]
    window = 1000
    parts = windows(chunks, window_tokens=window)
    long_summary = GOOD["summary"] + " Detail about this part of the lecture." * 25
    part_notes = [dict(GOOD, summary=long_summary, chapters=[{"title": f"Part {i}", "start_chunk": p[0].sequence}]) for i, p in enumerate(parts)]
    provider = FakeProvider(part_notes + [GOOD] * 10)
    result, report = await generate(provider, chunks, window_tokens=window)

    assert report.windows == len(parts) >= 4, len(parts)
    assert report.reduce_levels >= 1
    syntheses = [user for _, user in provider.prompts if "<part_notes>" in user]
    assert len(syntheses) >= 2  # at least one intermediate merge plus the final synthesis
    assert all(len(user) // 3 < window * 2 for user in syntheses)  # every merge request stays bounded
    assert result["summary"]


# --- OpenAI-compatible provider -------------------------------------------------------------------

import httpx  # noqa: E402

from app.services import llm as llm_module  # noqa: E402
from app.services.llm import OpenAICompatibleProvider  # noqa: E402


def provider_with(responses, settings, monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(llm_module.asyncio, "sleep", fake_sleep)
    queue = list(responses)

    def handler(request):
        return queue.pop(0)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(http, settings), slept


def ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}})


async def test_rate_limits_are_waited_out_as_instructed(settings, monkeypatch):
    provider, slept = provider_with(
        [httpx.Response(429, headers={"retry-after": "7.5"}, json={}), ok('```json\n{"a": 1}\n```')], settings, monkeypatch
    )
    assert await provider.generate_json("s", "u") == {"a": 1}
    assert slept == [7.5] and provider.usage.rate_limited_seconds == 7.5 and provider.usage.calls == 1


async def test_oversized_request_gets_an_actionable_error(settings, monkeypatch):
    provider, _ = provider_with([httpx.Response(413, json={"error": {"message": "Request too large"}})], settings, monkeypatch)
    with pytest.raises(LLMError) as caught:
        await provider.generate_json("s", "u")
    assert caught.value.code == "llm_request_too_large" and not caught.value.retryable
    assert "LLM_WINDOW_TOKENS" in caught.value.message


@pytest.mark.parametrize("status,code,retryable", [(401, "llm_rejected", False), (503, "llm_unavailable", True)])
async def test_provider_errors_are_classified(settings, monkeypatch, status, code, retryable):
    provider, _ = provider_with([httpx.Response(status, json={})], settings, monkeypatch)
    with pytest.raises(LLMError) as caught:
        await provider.generate_json("s", "u")
    assert (caught.value.code, caught.value.retryable) == (code, retryable)


async def test_non_json_output_is_retryable(settings, monkeypatch):
    provider, _ = provider_with([ok("Sure! Here are your notes.")], settings, monkeypatch)
    with pytest.raises(LLMError) as caught:
        await provider.generate_json("s", "u")
    assert caught.value.code == "llm_invalid_output" and caught.value.retryable


async def test_provider_json_mode_rejection_is_a_retryable_bad_output(settings, monkeypatch):
    body = {"error": {"code": "json_validate_failed", "message": "Failed to validate JSON.", "failed_generation": ""}}
    provider, _ = provider_with([httpx.Response(400, json=body)], settings, monkeypatch)
    with pytest.raises(LLMError) as caught:
        await provider.generate_json("s", "u")
    assert caught.value.code == "llm_invalid_output" and caught.value.retryable


async def test_reasoning_effort_is_sent_only_when_configured(settings):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return ok('{"a": 1}')

    for effort in ("", "low"):
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        configured = settings.model_copy(update={"llm_reasoning_effort": effort})
        await OpenAICompatibleProvider(http, configured).generate_json("s", "u")
    assert "reasoning_effort" not in seen[0] and seen[1]["reasoning_effort"] == "low"


async def test_one_bad_generation_is_asked_again_before_failing():
    provider = FakeProvider([LLMError("llm_invalid_output", "bad", retryable=True), GOOD])
    result, _ = await generate(provider, chunk_refs(6), window_tokens=100_000)
    assert len(provider.prompts) == 2 and result["summary"]


async def test_grounded_details_from_parts_are_carried_into_the_final_notes():
    chunks = chunk_refs(8)
    parts = windows(chunks, window_tokens=40)
    part_notes = [dict(GOOD, chapters=[{"title": f"Part {i}", "start_chunk": p[0].sequence}]) for i, p in enumerate(parts)]
    final = {key: value for key, value in GOOD.items() if key not in ("definitions", "keywords", "examples")}
    provider = FakeProvider([*part_notes, final])
    result, _ = await generate(provider, chunks, window_tokens=40)

    synthesis_prompt = provider.prompts[-1][1]
    assert '"keywords"' not in synthesis_prompt and '"examples"' not in synthesis_prompt  # not re-generated
    single = validate(GOOD, chunks, GenerationReport())
    assert result["definitions"] == single["definitions"]  # de-duplicated across parts
    assert sorted(result["keywords"]) == sorted(single["keywords"]) and result["examples"] == single["examples"]
