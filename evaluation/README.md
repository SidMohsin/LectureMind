# LectureMind — Evaluation Module

This folder contains standalone evaluation scripts for each major component
of the LectureMind pipeline, as described in the project synopsis (Section
3.7, Evaluation Metrics). These scripts are **separate from the running
application** — they do not need the FastAPI server to be running (except
`retrieval.py` and `qa_evaluation.py`, which import the backend's Python
services directly).

No accuracy numbers are fabricated anywhere in this codebase. All scripts
require you to supply reference/gold data before they will produce a
result, and they only report on the data you provide.

## Install evaluation dependencies

```
cd evaluation
pip install -r requirements.txt --break-system-packages
```

(Omit `--break-system-packages` if you're using a virtual environment,
which is recommended — see the root README.)

## Scripts

| Script | Metric | What it needs |
|---|---|---|
| `wer.py` | Word Error Rate (transcription) | Reference transcript text vs. LectureMind's transcript output |
| `summarization.py` | ROUGE, BERTScore (summarization) | Reference summary vs. LectureMind's generated summary |
| `retrieval.py` | Recall@k, Precision@k (retrieval) | A processed+indexed lecture_id, and a gold set of relevant chunk_ids per query |
| `qa_evaluation.py` | Grounding ratio, response latency, lexical overlap proxy for correctness | A processed lecture_id, and gold questions (with optional reference answers) |
| `keywords_evaluation.py` | Precision, Recall, F1 (keyword extraction) | Reference keyword list vs. LectureMind's extracted keywords |

## Which public dataset suits which component

- **TED-LIUM / TED Talks**: natural spoken English with reference transcripts —
  use with `wer.py` to evaluate Whisper transcription accuracy on longer,
  natural speech. Download from https://www.openslr.org/51/, place audio
  files under `evaluation/sample_data/` and pass the matching reference
  transcript text file to `--reference`.
- **LibriSpeech**: a standard, clean ASR benchmark (audiobooks) — good for a
  first sanity check of the Whisper component in isolation, before testing on
  noisier real lecture recordings. Download from https://www.openslr.org/12/.
- **AMI Meeting Corpus**: multi-speaker recordings with background noise —
  use for a more realistic stress-test of both `wer.py` (transcription under
  harder conditions) and `summarization.py` (meeting/lecture-style
  summarization). Download from https://groups.inf.ed.ac.uk/ami/download/.
- **LectureBank**: lecture slides and topic-labelled academic material (not
  audio) — use to build a reference keyword list per topic for
  `keywords_evaluation.py`, by manually pulling the terms associated with a
  slide deck that matches your demo lecture's topic. Available at
  https://github.com/Yale-LILY/LectureBank.

Do not download these datasets automatically as part of a normal run —
they are large. Download only the specific files you need for the
evaluation you're running, and place them under `evaluation/sample_data/`.

## Expected input formats

See the JSON files already included in `evaluation/sample_data/` as
templates:
- `gold_retrieval.json` — list of `{query, relevant_chunk_ids}`
- `gold_qa.json` — list of `{question, reference_answer}`
- `reference_keywords.json` — flat list of reference keyword strings
- `sample_transcript_reference.txt` — plain reference transcript text

## Example commands

```
# WER (standalone, no server needed)
python wer.py --reference sample_data/sample_transcript_reference.txt --hypothesis my_lecture_transcript.txt

# Summarization quality
python summarization.py --reference my_reference_summary.txt --hypothesis my_generated_summary.txt

# Retrieval Recall@k / Precision@k (uses backend services directly)
cd ../backend
python ../evaluation/retrieval.py --lecture_id <your_lecture_id> --gold_json ../evaluation/sample_data/gold_retrieval.json --k 5

# QA grounding + latency
python ../evaluation/qa_evaluation.py --lecture_id <your_lecture_id> --gold_json ../evaluation/sample_data/gold_qa.json

# Keyword extraction Precision/Recall/F1
cd ../evaluation
python keywords_evaluation.py --reference_json sample_data/reference_keywords.json --hypothesis_json my_generated_keywords.json
```

To get `my_lecture_transcript.txt` / `my_generated_summary.txt` /
`my_generated_keywords.json`, fetch them from the running application via
its API (`GET /api/lectures/{lecture_id}/transcript`, `/summary`,
`/keywords`) and save the relevant text/JSON to a file.

## Note on QA correctness

Fully automated correctness scoring for open-ended answers is an open
research problem. `qa_evaluation.py` reports a lexical-overlap proxy
(ROUGE-L against a reference answer) alongside the grounding ratio and
latency — this is a reasonable minor-project approach, but for the final
report it should be supplemented with a short manual review of the
generated answers, which is standard practice in RAG/QA evaluation.
