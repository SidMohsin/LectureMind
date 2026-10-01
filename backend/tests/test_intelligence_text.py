"""Transcript cleaning and chunking: pure, deterministic, timestamp-preserving."""

import re

import pytest

from app.intelligence.chunking import Segment, build_chunks, estimate_tokens
from app.intelligence.cleaning import RawSegment, clean_segments

# --- cleaning ---------------------------------------------------------------------------------


def raw(i, text, **kw):
    return RawSegment(sequence=i, start=i * 5.0, end=i * 5.0 + 4.5, text=text, **kw)


def test_cleaning_normalizes_formatting_without_changing_words():
    cleaned, stats = clean_segments([raw(0, "  so   today we'll talk about  , gradient descent .  ")])
    assert cleaned == ["So today we'll talk about, gradient descent."]
    assert stats.changed_segments == 1


def test_cleaning_never_adds_words():
    segments = [raw(0, " the loss function"), raw(1, "is convex ( mostly ) ."), raw(2, "  and so on")]
    cleaned, _ = clean_segments(segments)
    for before, after in zip(segments, cleaned):
        words_before = re.findall(r"\w+", before.text.lower())
        words_after = re.findall(r"\w+", after.lower())
        assert words_after == words_before


def test_cleaning_only_capitalizes_at_sentence_starts():
    cleaned, _ = clean_segments([raw(0, "we minimize the cost"), raw(1, "over theta."), raw(2, "next we")])
    assert cleaned == ["We minimize the cost", "over theta.", "Next we"]


def test_whisper_repetition_loops_are_collapsed_but_emphasis_kept():
    cleaned, stats = clean_segments([raw(0, "Thank you. Thank you. Thank you. Thank you."), raw(1, "It is very, very important.")])
    assert cleaned == ["Thank you.", "It is very, very important."]
    assert stats.collapsed_repetitions == 3


def test_duplicate_and_non_speech_segments_are_removed_in_place():
    segments = [
        raw(0, "Welcome to the class."),
        raw(1, "Welcome to the class."),
        raw(2, "Thanks for watching!", no_speech_prob=0.93, avg_logprob=-1.4),
        raw(3, "Let's begin."),
    ]
    cleaned, stats = clean_segments(segments)
    assert cleaned == ["Welcome to the class.", "", "", "Let's begin."]  # one entry per segment: timing preserved
    assert stats.removed_duplicate_segments == 1 and stats.removed_non_speech_segments == 1


def test_uncertain_but_speech_segments_are_kept():
    cleaned, _ = clean_segments([raw(0, "Eigenvalues.", no_speech_prob=0.5, avg_logprob=-1.5)])
    assert cleaned == ["Eigenvalues."]


# --- chunking ---------------------------------------------------------------------------------


def lecture(sentences_per_segment=2, segments=60):
    words = "the model learns parameters by minimizing a loss over training examples".split()
    out = []
    for i in range(segments):
        sentence = " ".join(words[(i + k) % len(words)] for k in range(9))
        text = " ".join(f"{sentence.capitalize()}." for _ in range(sentences_per_segment))
        out.append(Segment(sequence=i, start=i * 6.0, end=i * 6.0 + 5.8, text=text))
    return out


CONFIG = {"min_tokens": 200, "max_tokens": 400, "overlap_tokens": 50}


def test_chunks_are_non_empty_ordered_and_within_the_target_range():
    chunks = build_chunks(lecture(), **CONFIG)
    assert len(chunks) > 3
    assert [c.sequence for c in chunks] == list(range(len(chunks)))
    for chunk in chunks[:-1]:
        assert chunk.text.strip()
        assert 200 <= chunk.token_estimate <= 400 + 60  # a close may overshoot by at most one segment
    assert all(c.token_estimate > 0 for c in chunks)


def test_chunks_end_at_sentence_boundaries_and_keep_exact_segment_timestamps():
    segments = lecture()
    by_seq = {s.sequence: s for s in segments}
    for chunk in build_chunks(segments, **CONFIG):
        assert chunk.text.rstrip().endswith(".")
        assert chunk.start == by_seq[chunk.first_segment].start
        assert chunk.end == by_seq[chunk.last_segment].end
        assert chunk.end >= chunk.start


def test_overlap_is_consistent_and_every_segment_is_covered():
    segments = lecture()
    chunks = build_chunks(segments, **CONFIG)
    for previous, current in zip(chunks, chunks[1:]):
        shared = previous.last_segment - current.first_segment + 1
        assert shared >= 0
        overlap_text = " ".join(s.text for s in segments[current.first_segment : current.first_segment + shared])
        assert estimate_tokens(overlap_text) <= CONFIG["overlap_tokens"] if shared else True
    covered = {i for c in chunks for i in range(c.first_segment, c.last_segment + 1)}
    assert covered == {s.sequence for s in segments}


def test_chunking_is_deterministic_and_skips_removed_segments():
    segments = lecture()
    segments[5] = Segment(5, segments[5].start, segments[5].end, "")
    first = build_chunks(segments, **CONFIG)
    assert first == build_chunks(segments, **CONFIG)
    assert all("  " not in c.text for c in first)


def test_short_lecture_gives_one_chunk():
    chunks = build_chunks([Segment(0, 0.0, 3.2, "Hello and welcome."), Segment(1, 3.2, 6.0, "Today is short.")], **CONFIG)
    assert len(chunks) == 1 and chunks[0].start == 0.0 and chunks[0].end == 6.0


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        build_chunks([], min_tokens=400, max_tokens=200, overlap_tokens=50)
