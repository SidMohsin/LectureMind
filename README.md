# LectureMind: A Lecture Intelligence System

**Using Whisper, Retrieval-Augmented Generation and Large Language Models**

M.Tech Minor Project (MDS-393) — Mo Mohsin Siddique (25MDS021), Department of
Computer Engineering, Jamia Millia Islamia, under the supervision of
Prof. Tanvir Ahmad.

---

## 1. Project Description

LectureMind converts a recorded lecture (audio or video) into a searchable,
question-answerable knowledge source. It transcribes the lecture with
timestamps preserved, cleans and chunks the transcript, indexes it in a
vector database, and lets a student ask natural-language questions that are
answered using **only** the lecture's own content (Retrieval-Augmented
Generation). It also produces a structured summary and a list of important
keywords, and displays everything on a single student dashboard.

## 2. Features

- Professional application shell: sidebar navigation, dashboard, lecture library, dedicated upload and settings pages
- Light/dark mode with persisted preference
- Upload lecture video (MP4/MKV/MOV/AVI) or audio (MP3/WAV/M4A) with drag-and-drop, client + server-side validation
- Automatic audio extraction via FFmpeg
- Speech-to-text transcription with faster-whisper, timestamps preserved per segment
- Transcript cleaning (disfluency removal, punctuation/whitespace normalisation)
- Timestamp-aware overlapping chunking (configurable size/overlap)
- Local sentence embeddings (`all-MiniLM-L6-v2`) — no paid embedding API
- ChromaDB vector indexing and top-k semantic retrieval
- Grounded RAG chatbot — explicitly refuses to answer when the lecture doesn't contain the information, with suggested questions and a "clear conversation" option
- Hierarchical (chunk → intermediate summary → final structured summary) lecture summarization, shown as structured cards
- LLM-based keyword extraction with an automatic TF-IDF fallback; keywords are clickable and jump to a transcript search
- Modular LLM backend: local Ollama (default) or OpenAI/Groq via API key
- HTML5 media player (video or audio) streamed from the backend with HTTP Range support for seeking
- Real timestamp synchronization: clicking a transcript timestamp or a chat source seeks the media player; playback position highlights the active transcript segment
- Searchable transcript with match highlighting
- Lecture library: search, filter by status, sort, delete (with confirmation)
- Dashboard stats (total lectures, processed lectures, total duration, questions asked) derived from real backend data
- Download transcript as `.txt` or `.json`
- Settings page showing the backend's current non-secret configuration (LLM provider/model, embedding model, Whisper model, Top-K, chunking config)
- Background processing with live status polling and a genuine stage-by-stage progress indicator — the UI never freezes and never shows a fabricated percentage
- Empty, loading (skeleton), and error states throughout — no raw stack traces reach the UI
- Responsive layout (sidebar collapses on tablet/mobile)
- Optional evaluation suite: WER, ROUGE, BERTScore, Recall@k/Precision@k, QA grounding + latency, keyword P/R/F1

## 3. Architecture

```
Lecture Upload (Audio/Video)
        │
        ▼
Audio Extraction (FFmpeg)
        │
        ▼
Whisper ASR (faster-whisper) ──► Timestamped Transcript
        │
        ▼
Transcript Cleaning
        │
        ▼
Timestamp-aware Chunking
        │
   ┌────┴─────────────────┬──────────────────┐
   ▼                       ▼                  ▼
Sentence Embeddings   Summary Generation  Keyword Extraction
   │                       │                  │
   ▼                       │                  │
ChromaDB Vector DB          │                  │
   │                       │                  │
   ▼                       │                  │
Semantic Retrieval (top-k)  │                  │
   │                       │                  │
   ▼                       │                  │
RAG Context + LLM           │                  │
   │                       │                  │
   ▼                       ▼                  ▼
Grounded QA/Chatbot ──► Student Dashboard ◄─────
```

This mirrors the block diagram, system architecture and flowchart in the
project synopsis (Sections 3.4–3.6).

## 4. Technology Stack

**Frontend:** React 18, Vite, plain modern CSS (no UI framework), fetch/XHR-based API client.

**Backend:** Python 3.10+, FastAPI, Uvicorn, SQLAlchemy + SQLite, BackgroundTasks for async processing.

**AI/ML components:**
- ASR: faster-whisper (CTranslate2 reimplementation of OpenAI Whisper)
- Embeddings: sentence-transformers (`all-MiniLM-L6-v2`), local, free
- Vector DB: ChromaDB (persistent, local)
- LLM: Ollama (local, default) or OpenAI/Groq (optional, via API key)

**Media processing:** FFmpeg (external system dependency)

## 5. System Requirements

- Windows 10/11 (instructions below; the same commands work on macOS/Linux with minor path differences)
- Python 3.10 or 3.11
- Node.js 18+ and npm
- FFmpeg installed and on PATH
- ~5 GB free disk space (Whisper model + embedding model + Python packages)
- If using Ollama: ~5 GB additional disk space for the `llama3.1:8b` model, and a reasonably modern CPU (8GB+ RAM recommended)
- No GPU required (faster-whisper runs on CPU with `int8` quantization by default)

---

## 6. Installation (Windows 10/11)

### 6.1 Install Python

1. Download Python 3.11 from https://www.python.org/downloads/
2. During installation, **check "Add python.exe to PATH"**
3. Verify in a new Command Prompt:
   ```
   python --version
   ```

### 6.2 Install Node.js

1. Download the LTS installer from https://nodejs.org/
2. Install with default options
3. Verify:
   ```
   node --version
   npm --version
   ```

### 6.3 Install FFmpeg

1. Download a Windows build from https://www.gyan.dev/ffmpeg/builds/ (choose the "release full" zip)
2. Extract it, e.g. to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to your system PATH:
   - Search "Environment Variables" in Windows Start Menu → Edit the system environment variables → Environment Variables → under "System variables" select `Path` → Edit → New → paste `C:\ffmpeg\bin`
4. Open a **new** Command Prompt and verify:
   ```
   ffmpeg -version
   ```

### 6.4 Install Ollama (if using the default local LLM)

1. Download and install from https://ollama.com
2. Open a Command Prompt and pull the model:
   ```
   ollama pull llama3.1:8b
   ```
3. Ollama runs its API server automatically in the background after installation. You can verify it's running with:
   ```
   ollama list
   ```
   If it's not running, start it with:
   ```
   ollama serve
   ```

> If `llama3.1:8b` is too large/slow for your laptop, you can instead pull a
> smaller model (e.g. `ollama pull llama3.2:3b`) and set `OLLAMA_MODEL=llama3.2:3b`
> in your `.env` file. Alternatively, configure OpenAI or Groq instead (see Section 7).

### 6.5 Clone / place the project

Place the `LectureMind/` folder anywhere, e.g. `C:\Projects\LectureMind`.

### 6.6 Create a Python virtual environment and install backend packages

```
cd LectureMind\backend
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

> The first time you run the backend, faster-whisper and sentence-transformers
> will download their model weights automatically (a few hundred MB total) —
> this requires an internet connection on first run only.

### 6.7 Install frontend packages

```
cd ..\frontend
npm install
```

### 6.8 Create your `.env` file

```
cd ..\backend
copy ..\.env.example .env
```

Edit `backend\.env` with a text editor and set `LLM_PROVIDER` and the
matching model/keys (see Section 7 below). The defaults work out of the box
if you've installed Ollama as described above.

---

## 7. Configuration

All configuration lives in `backend/.env` (copied from the root
`.env.example`). Key settings:

```
LLM_PROVIDER=ollama            # or: openai, groq
OLLAMA_MODEL=llama3.1:8b
WHISPER_MODEL_SIZE=base        # tiny/base/small/medium/large-v3
CHUNK_SIZE_WORDS=650
CHUNK_OVERLAP_WORDS=120
TOP_K=5
```

To use OpenAI instead of Ollama:
```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...your-key...
OPENAI_MODEL=gpt-4o-mini
```

To use Groq instead:
```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...your-key...
GROQ_MODEL=llama-3.1-8b-instant
```

No API key is ever hard-coded in the source code — all secrets are read
from environment variables only. If a required key/model is missing, the
API returns a clear error message instead of crashing.

---

## 8. Running the Application

### 8.1 Start the backend

```
cd LectureMind\backend
venv\Scripts\activate
uvicorn app.main:app --reload
```

Backend runs at **http://localhost:8000**. Interactive API docs at
**http://localhost:8000/docs**.

### 8.2 Start the frontend (in a separate terminal)

```
cd LectureMind\frontend
npm run dev
```

Frontend runs at **http://localhost:5173**.

### 8.3 Open the application

Open **http://localhost:5173** in your browser.

---

## 9. First-Time Setup / First Test

1. Make sure both backend and frontend are running (Section 8), and Ollama
   is running (`ollama serve`) if using the default local LLM.
2. In the browser, drag a short lecture clip (a few minutes of MP4 or MP3 is
   ideal for a first test) into the upload box and click **Upload Lecture**.
3. Processing starts automatically. Watch the status stepper move through:
   Extracting audio → Transcribing with Whisper → Cleaning transcript →
   Creating chunks → Generating embeddings → Indexing in ChromaDB →
   Generating summary → Extracting keywords → Completed.
4. Once completed, click the **Transcript** tab to see the timestamped
   transcript, **Summary** for the structured summary, **Keywords** for the
   extracted terms.
5. Click the **Chat** tab and ask a question about the lecture content, e.g.
   "What is the main topic discussed?" You should see a grounded answer with
   clickable source timestamps below it.
6. Ask a question that is clearly unrelated to the lecture — you should see
   the response: *"I could not find sufficient information about this in
   the uploaded lecture."*

---

## 10. How the Pipeline Works (Module Explanations)

- **`audio.py`** — Calls FFmpeg via subprocess to extract/convert any input
  video or audio into a standard 16kHz mono PCM WAV file, since ASR models
  expect a consistent sample rate and channel count.
- **`whisper_service.py`** — Loads a faster-whisper model once (cached) and
  transcribes the WAV file with VAD (voice activity detection) filtering to
  skip silence, returning segments each with `start`, `end`, `text`.
- **`transcript.py`** — Cleans each segment's text (whitespace, punctuation,
  filler-word removal) without ever touching the timestamps.
- **`chunking.py`** — Merges segments into ~650-word overlapping chunks by
  building a per-word timestamp stream (interpolated within each segment)
  so every chunk knows its accurate start/end time, even though chunk
  boundaries don't align with segment boundaries.
- **`embeddings.py`** — Uses `sentence-transformers/all-MiniLM-L6-v2`
  (384-dim, runs on CPU) to convert each chunk into a normalized vector.
- **`vector_store.py`** — Wraps ChromaDB; each lecture gets its own
  collection so lectures never mix during retrieval.
- **`retrieval.py`** — Embeds the student's query with the same model and
  asks ChromaDB for the top-k nearest chunks.
- **`rag.py`** — Builds a context block from the retrieved chunks, sends it
  to the LLM with an explicit "only use this context, and say so if you
  can't find the answer" system prompt, and returns the answer plus sources.
- **`summarizer.py`** — Hierarchical summarization: splits the transcript
  into ~700-word pieces, summarizes each independently, then asks the LLM
  to combine those partial summaries into one structured JSON summary
  (overview / main concepts / important points / key takeaways).
- **`keywords.py`** — Asks the LLM for 10–20 keywords as JSON; if that call
  or its JSON parsing fails, falls back to a TF-IDF ranking over the
  transcript's sentences using scikit-learn, so keyword extraction never
  hard-fails.
- **`llm_provider.py`** — A single `generate(system_prompt, user_prompt)`
  function that routes to Ollama's local REST API or an OpenAI-compatible
  chat completions endpoint (OpenAI or Groq), based on `LLM_PROVIDER`.
- **`pipeline.py`** — Orchestrates all of the above as a background task,
  updating the lecture's `status` field at each stage so the frontend can
  poll and show progress without blocking.

## 11. API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/lectures/upload` | Upload a lecture file |
| POST | `/api/lectures/{lecture_id}/process` | Start the processing pipeline (background) |
| GET | `/api/lectures/{lecture_id}/status` | Poll processing status |
| GET | `/api/lectures/{lecture_id}` | Full lecture metadata (used by the workspace page) |
| GET | `/api/lectures/{lecture_id}/transcript` | Get timestamped transcript |
| GET | `/api/lectures/{lecture_id}/summary` | Get structured summary |
| GET | `/api/lectures/{lecture_id}/keywords` | Get extracted keywords |
| GET | `/api/lectures/{lecture_id}/media` | Stream the original media file (Range-request enabled, powers the player) |
| POST | `/api/lectures/{lecture_id}/chat` | Ask a question (RAG) |
| DELETE | `/api/lectures/{lecture_id}` | Delete a lecture and all its files/index data |
| GET | `/api/lectures` | List all uploaded lectures |
| GET | `/api/stats` | Aggregate dashboard stats (real, derived from stored data) |
| GET | `/api/config` | Non-secret current configuration (for the Settings page) |
| GET | `/api/health` | Health check |

Full interactive documentation (request/response schemas) is available at
`http://localhost:8000/docs` while the backend is running.

## 12. Project Structure

```
LectureMind/
├── backend/
│   ├── app/
│   │   ├── main.py, config.py, database.py
│   │   ├── models/lecture.py
│   │   ├── schemas/lecture.py
│   │   ├── api/lectures.py
│   │   ├── services/  (audio, whisper_service, transcript, chunking,
│   │   │               embeddings, vector_store, retrieval, rag,
│   │   │               summarizer, keywords, llm_provider, pipeline)
│   │   └── utils/file_validation.py
│   ├── data/ (uploads, audio, transcripts, summaries, chroma, metadata)
│   ├── requirements.txt
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── components/ (Sidebar, Topbar, StatCard, LectureRow, UploadZone,
│   │   │                ProcessingStages, MediaPlayer, TranscriptPanel,
│   │   │                SummaryPanel, KeywordsPanel, ChatPanel, StatusBadge,
│   │   │                EmptyState, ErrorState, Skeleton, ConfirmDialog)
│   │   ├── pages/ (Dashboard, Library, UploadPage, Settings, LectureWorkspace)
│   │   ├── context/AppContext.jsx (navigation + theme)
│   │   ├── services/ (api.js, format.js)
│   │   ├── App.jsx, main.jsx, index.css
│   ├── package.json
│   └── README.md
├── evaluation/
│   ├── wer.py, summarization.py, retrieval.py, qa_evaluation.py, keywords_evaluation.py
│   ├── sample_data/
│   └── README.md
├── .env.example
├── .gitignore
└── README.md   (this file)
```

## 13. Troubleshooting

| Problem | Fix |
|---|---|
| `ffmpeg: command not found` / audio extraction fails | Re-check Section 6.3 — FFmpeg must be on PATH. Open a **new** terminal after editing PATH. |
| Backend fails to start: `ModuleNotFoundError` | Make sure the virtual environment is activated (`venv\Scripts\activate`) and `pip install -r requirements.txt` completed without errors. |
| Frontend shows "Network error" on upload | Confirm the backend is running at `http://localhost:8000` and `CORS_ORIGINS` in `.env` includes `http://localhost:5173`. |
| Processing stuck at "Transcribing" for a long time | This is expected for `WHISPER_MODEL_SIZE=medium` or `large-v3` on CPU — use `base` or `small` for faster demos. |
| Chat returns "LLM not configured" | If using Ollama, confirm `ollama serve` is running and `ollama pull llama3.1:8b` completed. If using OpenAI/Groq, confirm the API key is set in `.env` and the backend was restarted after editing `.env`. |
| Chatbot always says "could not find sufficient information" | Check that processing actually reached `completed` status (see `/api/lectures/{id}/status`) — chunks must be indexed in ChromaDB before retrieval works. |
| `pip install` fails on `chromadb` or `sentence-transformers` | Ensure you're using Python 3.10 or 3.11 (some ML packages lag behind the newest Python releases); reinstall with `pip install -r requirements.txt` inside a clean venv. |
| Upload rejected as "Unsupported file type" | Only MP4/MKV/MOV/AVI (video) and MP3/WAV/M4A (audio) are accepted — check the file extension. |
| Upload rejected as too large | Increase `MAX_UPLOAD_SIZE_MB` in `.env` (default 500 MB) and restart the backend. |
| Video/audio player shows but won't play or seek | Confirm you can reach `http://localhost:8000/api/lectures/{id}/media` directly in the browser — if that 404s, the original uploaded file may have been moved/deleted from `backend/data/uploads/`. Seeking specifically relies on HTTP Range support, which the backend implements — if you're running behind a custom proxy, make sure it forwards `Range`/`Accept-Ranges` headers. |
| Transcript doesn't highlight while playing / clicking a timestamp doesn't seek | This requires the media player to be present (i.e. the original file still exists on disk) — a lecture processed from a file that was later deleted will show `has_media: false` and the player won't render. |
| Dashboard stats show 0 for everything | Stats are computed live from the database — this is expected before any lecture has been uploaded and processed. |
| Deleting a lecture appears to succeed but files remain on disk | Check the backend log — file deletion is best-effort (a missing file won't block the operation), but a permissions error on Windows would be printed there. |
| Settings page fails to load | Confirm the backend is reachable at the configured `VITE_API_BASE_URL` — `GET /api/config` must return 200. |

## 14. Evaluation

See `evaluation/README.md` for full details. In short:

- `wer.py` — Word Error Rate for transcription
- `summarization.py` — ROUGE + BERTScore for summaries
- `retrieval.py` — Recall@k / Precision@k for the retriever
- `qa_evaluation.py` — Grounding ratio, response latency, lexical-overlap correctness proxy
- `keywords_evaluation.py` — Precision/Recall/F1 for keyword extraction

All scripts require you to supply reference/gold data; no numbers are
fabricated or pre-filled.

## 15. Future Scope

(As outlined in the synopsis, Section 5) Adaptive/personalised learning,
hallucination-aware RAG with confidence checks, flashcard/MCQ generation,
multilingual support, PDF/slide integration into the same retrieval index,
learning analytics, and voice-based question answering.

## 16. Limitations

- Runs entirely on a single machine; not designed for concurrent multi-user production load.
- Whisper transcription accuracy depends on audio quality and the chosen model size.
- Local LLMs (via Ollama) are less capable than large hosted models — summaries and
  answers may be less polished than with GPT-4-class models, particularly on the
  smaller model sizes.
- Per-word timestamps within a chunk are linearly interpolated from segment-level
  timestamps (Whisper does not natively provide word-level timestamps in this
  configuration), so chunk boundary timestamps are approximate, not frame-exact.
- No authentication/multi-tenancy — this is a single-user demo/prototype, per the
  synopsis's minor-project scope.
- The media player streams the original uploaded file directly from local disk;
  if that file is moved or deleted after processing, playback and timestamp
  seeking become unavailable for that lecture (the transcript/summary/keywords/
  chat remain fully available, since those don't depend on the original file).
- "Questions Asked" on the dashboard counts all chat messages ever sent across
  all lectures (from the `chat_logs` table) — it is not scoped per-lecture or
  per-session.
- Deleting a lecture is irreversible: it removes the database row, the
  uploaded/extracted files, and the ChromaDB collection. There is no trash/undo.
- Transcript search, keyword-to-search, and download are implemented entirely
  client-side against already-fetched data — they do not require or use any
  additional backend endpoint beyond what's listed in Section 11.

---

## 17. Viva Questions (for demonstration)

**Whisper / ASR**
- Why was Whisper (via faster-whisper) chosen over other ASR systems?
- How does Whisper produce timestamps, and why are they important here?
- What is the effect of the `WHISPER_MODEL_SIZE` setting on accuracy vs. speed?
- What is VAD filtering and why is it used before transcription?

**Embeddings & Semantic Search**
- What is a sentence embedding, and how does `all-MiniLM-L6-v2` represent meaning?
- Why does semantic search outperform keyword search for this use case?
- Why normalize embeddings before storing/comparing them?

**ChromaDB & Chunking**
- Why split a transcript into overlapping chunks instead of embedding the whole transcript at once?
- How is timestamp information preserved through chunking, given that chunk boundaries don't align with Whisper segment boundaries?
- What would happen to retrieval quality with too-small or too-large a chunk size?

**RAG**
- What problem does Retrieval-Augmented Generation solve compared to asking an LLM directly?
- Walk through the exact RAG pipeline steps in LectureMind, end to end.
- Why is `top_k` configurable, and what's the trade-off in choosing it?

**LLM**
- Why was the LLM provider made modular (Ollama vs. OpenAI vs. Groq)?
- What happens if the configured LLM is unreachable, and how does the system fail gracefully?

**Hallucination**
- How does LectureMind reduce hallucination risk in the chatbot?
- What is the exact fallback behaviour when the answer isn't in the lecture?
- Why is this fallback checked programmatically (the `grounded` flag) rather than trusted blindly?

**Timestamp Preservation**
- Trace how a timestamp survives from the raw Whisper segment all the way to a clickable chat source.

**Summarization**
- Why use a hierarchical (map-reduce style) summarization approach instead of sending the whole transcript to the LLM?
- What structure does the final summary follow, and why?

**Evaluation Metrics**
- What does WER measure, and what are its limitations for evaluating a lecture transcription tool?
- Why use both ROUGE and BERTScore for summarization instead of just one?
- What is the difference between Recall@k and Precision@k in this retrieval context?
- How is QA "correctness" evaluated here, and why is it harder to automate than WER?

**Architecture & Design Choices**
- Why FastAPI + BackgroundTasks instead of a heavier task queue (e.g. Celery)?
- Why SQLite instead of PostgreSQL for this project?
- Why ChromaDB instead of a hosted vector database?
- What are the main failure points in the pipeline, and how does each one fail gracefully instead of crashing the whole request?

**Frontend & Media Streaming**
- How does the browser seek within a large video file without downloading the whole thing first? (Explain HTTP Range requests and the `206 Partial Content` response the `/media` endpoint returns.)
- How is playback position kept in sync with the highlighted transcript segment — what triggers the update, and how often?
- Why was navigation implemented as simple React state instead of a routing library like React Router?
- Why is transcript search implemented entirely on the client instead of adding a `/transcript/search` backend endpoint?
- What data does the "Questions Asked" dashboard stat actually come from, and what would happen to it if the chat history were cleared per-conversation instead of logged server-side?
