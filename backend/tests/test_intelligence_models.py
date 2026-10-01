"""Real speech-recognition and embedding models (downloads the models on first run).

Run with:  pytest -m models
Speech is synthesized offline with the Windows speech engine, so the expected
words are known without any fixture file.
"""

import subprocess
import sys

import pytest

from app.core.config import Settings
from app.intelligence.embeddings import FastEmbedEmbedder
from app.intelligence.transcription import FasterWhisperTranscriber, TranscriptionProgress

pytestmark = pytest.mark.models

SPOKEN = (
    "Gradient descent is an optimization algorithm. "
    "It updates the parameters in the direction of the negative gradient. "
    "The learning rate controls the step size."
)


@pytest.fixture(scope="module")
def settings():
    return Settings(_env_file=None, transcription_model="tiny.en", transcription_beam_size=1)


@pytest.fixture(scope="module")
def speech(tmp_path_factory):
    if sys.platform != "win32":
        pytest.skip("uses the Windows speech synthesizer")
    path = tmp_path_factory.mktemp("speech") / "lecture.wav"
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{SPOKEN}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    return path


def test_real_speech_is_transcribed_with_ordered_timestamps(settings, speech):
    progress = TranscriptionProgress()
    transcript = FasterWhisperTranscriber(settings).transcribe(speech, progress)

    text = " ".join(segment.text for segment in transcript.segments).lower()
    for phrase in ("gradient descent", "optimization algorithm", "learning rate", "step size"):
        assert phrase in text, text
    assert transcript.language == "en"
    starts = [s.start for s in transcript.segments]
    assert starts == sorted(starts)
    assert all(0 <= s.start <= s.end <= transcript.duration_seconds + 0.5 for s in transcript.segments)
    assert transcript.model == "faster-whisper/tiny.en"
    assert transcript.model_config["implementation"] == "faster-whisper" and transcript.model_config["vad_filter"] is True
    assert progress.processed_seconds > 0 and progress.total_seconds == pytest.approx(transcript.duration_seconds)


PASSAGES = {
    "gradient": "To train the model we use gradient descent: take the derivative of the cost and step against it, scaled by the learning rate.",
    "overfitting": "If the hypothesis has too many features it fits the training set perfectly but generalizes badly; that is overfitting, and regularization helps.",
    "bayes": "Naive Bayes assumes the features are conditionally independent given the class label, which makes the likelihood easy to estimate.",
    "svm": "A support vector machine finds the separating hyperplane with the largest margin between the two classes.",
}


@pytest.mark.parametrize(
    "query,expected",
    [
        ("How are the parameters updated during training?", "gradient"),
        ("Why does a model with many features perform poorly on new data?", "overfitting"),
        ("What independence assumption does the classifier make?", "bayes"),
        ("What is the maximum margin classifier?", "svm"),
    ],
)
def test_query_retrieves_the_relevant_passage(settings, query, expected):
    embedder = FastEmbedEmbedder(settings)
    keys = list(PASSAGES)
    passages = embedder.embed_passages([PASSAGES[k] for k in keys])
    query_vector = embedder.embed_query(query)

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b)) / ((sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5))

    ranked = sorted(keys, key=lambda k: cosine(query_vector, passages[keys.index(k)]), reverse=True)
    assert ranked[0] == expected, ranked
    assert all(len(v) == embedder.dimension == 384 for v in passages)
