# LectureMind

LectureMind is a Lecture Intelligence Platform that converts recorded lectures into a
structured, searchable, lecture-grounded knowledge asset: timestamped transcript,
chapters, key concepts, definitions, and grounded question answering with source
timestamps.

Full product/technical source of truth: the PRD, Architecture, Design, Roadmap, Memory
and Testing documents supplied with this project.

## Current status: Phase 7B — Hardening + Evaluation Foundation

Implemented so far:

- **Phase 1:** React + JavaScript frontend (Vite, React Router, design tokens, app shell,
  central API client) and FastAPI backend (config, logging, error handling, `/health`).
- **Phase 2:** Supabase Auth (sign up, verification, login, session restore, logout,
  password reset), protected routes, backend token verification, `profiles`/`lectures`
  with Row Level Security, and a private `lectures` storage bucket.
- **Phase 3:** Dashboard, Lecture Library (search, filters, sort, pagination, delete),
  the Ingest Lecture page, lecture routes and Settings.
- **Phase 4:** real ingestion of video/audio uploads and YouTube URLs, a Redis-backed job
  queue, a separate processing worker, FFmpeg audio extraction, a persistent processing
  lifecycle with retries, and a Processing Details page.
- **Phase 5:** timestamped transcription (faster-whisper), conservative transcript
  cleaning, sentence-aware chunking with overlap, sentence embeddings stored in pgvector
  (HNSW index + an RLS-respecting retrieval function), and grounded lecture intelligence
  (summary, chapters, topics, key concepts, definitions, keywords, important points,
  examples) from an LLM behind a provider interface. Every pipeline stage is implemented,
  so lectures now reach READY.
- **Phase 6:** the Lecture Workspace: private media playback (signed URLs, HTTP range),
  a transcript synchronized with playback (click-to-seek, find, follow playback),
  chapters and the stored lecture intelligence with clickable timestamps, and grounded
  lecture-specific Q&A (query embedding → pgvector retrieval → evidence threshold →
  bounded context → LLM → cited sources) with persisted question history.
- **Phase 7A:** Search: lecture metadata search, plus semantic search for passages across
  the user's own lectures, opening the lecture at the passage's timestamp. The Question
  History page: search, filter by lecture, order, paging, opening an answer back in its
  lecture at its source, and deleting questions (one, or all for a lecture).
- **Phase 7B:** per-user rate limits, security headers, safe logging with request ids,
  readiness checks, worker presence, stuck-job detection and a cap on re-running crashed
  jobs, an orphaned-media cleanup tool, a cross-user permission regression suite, and the
  offline research-evaluation framework (`backend/evaluation/`).

Not implemented yet: production deployment, and the formal evaluation itself. The
framework exists, but no evaluation dataset has been built or run, so **no research
metrics (WER, retrieval, answer correctness, citation support, abstention) are reported.**

## Project structure

```text
frontend/              React + JavaScript application (Vite, React Router)
backend/               FastAPI application + processing worker
  app/api/             Routers (health, me, lectures, ingestion) and auth dependencies
  app/core/            Config, token verification, errors, logging
  app/services/        Supabase access (user-scoped + service role), ingestion,
                       Redis queue, source-URL providers, LLM provider (llm.py)
  app/intelligence/    Transcription, cleaning, chunking, embeddings, grounded generation
  app/repositories/    Table-level queries
  app/workers/         Lifecycle rules, pipeline runner, stages, FFmpeg/ffprobe,
                       per-job workspaces, worker entry point (main.py)
  tests/               Offline unit tests; tests/integration = live Supabase/Redis suite
supabase/
  config.toml          Supabase CLI project config (auth settings mirror the hosted project)
  migrations/          Reproducible schema, RLS, storage policies and worker functions
```

## 1. Prerequisites

- Node.js 20+, Python 3.12+
- **FFmpeg + ffprobe** on `PATH` (or set `FFMPEG_PATH` / `FFPROBE_PATH`)
- **Redis** (any version; the queue uses only basic commands over RESP2). On Windows,
  `winget install Redis.Redis` installs a local service on port 6379.
- A Supabase project per environment (development / staging / production)

## 2. Supabase project setup

1. Create a project at supabase.com.
2. Apply the schema (via `npx`, no global install or Docker needed):

   ```bash
   npx supabase login
   npx supabase link --project-ref <project-ref>
   npx supabase db push
   ```

   Never change the schema by hand; add a migration (`npx supabase migration new <name>`).
3. Authentication → URL Configuration: Site URL `http://localhost:5173`; Redirect URLs
   `http://localhost:5173/verify` and `http://localhost:5173/reset-password`.
   Sign In / Providers → Email: Confirm email **on**, minimum password length **8**.
4. **Email delivery:** the built-in email service only reaches members of your Supabase
   organisation and sends about 2 emails per hour. Configure custom SMTP (Authentication →
   Emails) before other people sign up.
5. **Storage size:** Supabase's free plan limits each stored file to 50 MB. Set
   `MAX_VIDEO_BYTES` / `MAX_AUDIO_BYTES` to match your plan (the UI reads them from the
   API).

## 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env     # VITE_API_BASE_URL, VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY
npm run dev              # http://localhost:5173
npm test && npm run lint && npm run build
```

## 4. Backend API + worker

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements-dev.txt
cp .env.example .env            # fill in the Supabase values

uvicorn app.main:app --reload --port 8000     # terminal 1: API
python -m app.workers.main                    # terminal 2: processing worker
```

The API only validates, stores and queues; all heavy work (downloads, ffprobe, FFmpeg)
runs in the worker. Run more worker processes to process more lectures in parallel.

| Variable | Purpose |
|---|---|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | Project URL and anon/publishable key (user-scoped reads with RLS). |
| `SUPABASE_SERVICE_ROLE_KEY` | **Server-only.** Ingestion writes after ownership is verified, and the worker. Never in a `VITE_` variable. |
| `SUPABASE_JWT_SECRET` | Only for projects still on the legacy HS256 JWT secret. |
| `CORS_ALLOW_ORIGINS` | Comma-separated frontend origins. |
| `REDIS_URL` | Queue server (default `redis://127.0.0.1:6379/0`). |
| `WORK_DIR` | Scratch space for per-job files (default: system temp). |
| `FFMPEG_PATH`, `FFPROBE_PATH` | Binaries (default: from `PATH`). |
| `MAX_VIDEO_BYTES`, `MAX_AUDIO_BYTES`, `MAX_MEDIA_DURATION_SECONDS` | Authoritative ingestion limits. |
| `SOURCE_URL_DOWNLOADS_ENABLED` | Allow YouTube URL ingestion. |
| `WORKER_*` | Lease, heartbeat, recovery-sweep and retry-backoff timings. |
| `MODEL_CACHE_DIR` | Where speech/embedding models are downloaded (default `~/.cache/lecturemind-models`). |
| `TRANSCRIPTION_MODEL`, `_DEVICE`, `_COMPUTE_TYPE`, `_BEAM_SIZE`, `_LANGUAGE` | faster-whisper settings (default `small`, `cpu`, `int8`, 5, auto-detect). |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` | fastembed model (default `BAAI/bge-small-en-v1.5`, 384). The dimension must match the `vector(384)` column. |
| `CHUNK_MIN_TOKENS`, `CHUNK_MAX_TOKENS`, `CHUNK_OVERLAP_TOKENS` | Chunk size targets (200 / 400 / 50 estimated tokens). |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | Any OpenAI-compatible Chat Completions API (OpenAI, Groq, Gemini's OpenAI endpoint, Ollama). **Server-only.** |
| `LLM_WINDOW_TOKENS`, `LLM_MAX_OUTPUT_TOKENS` | Transcript per request and response cap. Lower both on providers with small per-minute token limits. |
| `LLM_TEMPERATURE`, `LLM_TIMEOUT_SECONDS`, `LLM_RATE_LIMIT_RETRIES`, `LLM_REASONING_EFFORT` | Generation settings; `LLM_REASONING_EFFORT=low` for reasoning models such as `gpt-oss`. |
| `RAG_TOP_K`, `RAG_MIN_SIMILARITY` | Chunks retrieved per question (6) and the minimum cosine similarity for a chunk to count as evidence (0.6). |
| `RAG_CONTEXT_TOKENS`, `RAG_MAX_OUTPUT_TOKENS`, `RAG_RATE_LIMIT_RETRIES` | Evidence budget per question, answer cap, and how many provider rate limits a question waits out. |
| `SEARCH_CANDIDATES`, `SEARCH_MIN_SIMILARITY`, `SEARCH_MAX_PER_LECTURE` | Semantic search: candidates ranked in the database (40), minimum cosine similarity to show a passage (0.6), and passages per lecture (3). |
| `PLAYBACK_AUDIO_BITRATE_KBPS`, `PLAYBACK_MIN_BITRATE_KBPS`, `PLAYBACK_MAX_BYTES` | Private playback audio for URL lectures (48 kbps AAC, lowered to fit 48 MB). |
| `MEDIA_URL_TTL_SECONDS` | Lifetime of signed media URLs given to the player (1 hour; the player renews an expired one). |

### Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Public health check. |
| `GET /me` | Caller's identity and profile. |
| `GET /lectures`, `GET /lectures/subjects`, `GET /lectures/{id}`, `DELETE /lectures/{id}` | The caller's library (each lecture includes its processing job summary). |
| `GET /ingestion/limits` | Accepted formats and size/duration limits. |
| `POST /lectures/uploads` | Multipart video/audio upload + metadata. `Idempotency-Key` header makes retries safe. |
| `POST /lectures/sources` | YouTube URL + metadata + rights confirmation. |
| `POST /lectures/{id}/retry` | Re-queue a failed, retryable job. |
| `GET /lectures/{id}/processing` | Job, per-stage runs with timings, and stored media facts. |
| `GET /lectures/{id}/workspace` | Transcript segments, chapters, lecture intelligence and chunk times (one call). |
| `GET /lectures/{id}/media` | A short-lived signed URL for the lecture's private media. |
| `POST /lectures/{id}/questions` | Ask a question about this lecture: grounded answer + sources, or insufficient evidence. |
| `GET /lectures/{id}/questions` | This lecture's question history for the caller, newest first. |
| `DELETE /lectures/{id}/questions` | Delete all of the caller's questions about one lecture. |
| `GET /search/content?q=` | Semantic search: passages from the caller's ready lectures, with lecture and timestamps. Metadata search is `GET /lectures?q=`. |
| `GET /questions` | The caller's question history across lectures (`q`, `lecture_id`, `order`, `limit`, `offset`). |
| `DELETE /questions/{id}` | Delete one of the caller's questions. |

### Tests

```bash
pytest                   # offline: API, lifecycle, pipeline, worker (real FFmpeg), queue
pytest -m integration    # live: Supabase auth/RLS/storage, ingestion + worker, pgvector retrieval, Redis
pytest -m models         # real faster-whisper + fastembed models (downloads them on first run)
pytest -m llm            # grounded Q&A + prompt-injection checks with the real configured LLM
```

Stop any running worker before `pytest -m integration`: a live worker on the same Redis
queue can pick up the test's job and run it through the full pipeline.

The live suite needs `backend/.env.test` (copy `.env.test.example`) pointing at a
**development** project. It creates and deletes throwaway `lecturemind-test-*` users.

## Processing architecture

```text
Upload / YouTube URL
  → API: auth, server-side validation (real file bytes, size, metadata, URL + availability)
  → lecture + media records, private storage, one processing job   (Postgres)
  → job id pushed to Redis                                         (notification only)
  → worker claims the job with a lease (database time), heartbeats while running
  → EXTRACTING_AUDIO: download to a private temp dir → ffprobe validation
    → FFmpeg → 16 kHz mono FLAC in the job's temp workspace (never uploaded)
    → URL lectures only: a private mono AAC playback file, processed/playback.m4a
  → TRANSCRIBING: faster-whisper with voice-activity filtering → timestamped segments
  → CLEANING: whitespace/punctuation fixes, removes non-speech and repeated segments;
    never adds words or changes timestamps (the raw text is kept alongside)
  → CHUNKING: whole segments → ~200-400-token chunks, sentence-aware, ~50-token overlap
  → EMBEDDING: fastembed (ONNX, no PyTorch) → 384-dim vectors
  → INDEXING: pgvector HNSW (cosine) + a self-retrieval check
  → GENERATING_INTELLIGENCE: LLM notes, grounded in cited chunks → READY
```

**Grounding.** The LLM sees the transcript as numbered, timestamped chunks marked as
untrusted data, and must cite chunk numbers for every item. The server then checks the
answer: items without valid citations are dropped, keywords and definition terms must
occur in the transcript, and chapter times come from the cited chunks rather than the
model. A bad answer gets one repair attempt. Long lectures are summarised in ordered parts,
merged level by level, then synthesised. Definitions, keywords and examples are carried
over from the validated part notes, not regenerated. Models, settings, timings, token
counts and dropped items are stored with the results for evaluation.

- **Source of truth:** Postgres. Redis only says "job X may be ready"; a worker must still
  claim the job, so duplicate or stale messages are harmless.
- **Recovery:** a periodic sweep re-queues jobs whose worker died (expired lease), delayed
  retries that are due, and notifications Redis lost. If Redis is down, due jobs are
  processed straight from the sweep.
- **Retries:** transient failures (storage/network, timeouts, unexpected errors) retry
  automatically with exponential backoff, up to 3 attempts. Permanent problems (corrupt or
  unreadable media, no audio track, too long, restricted source) fail immediately with a
  stored reason. Users can retry a retryable failure.
- **Idempotency:** one job per lecture; `Idempotency-Key` replay; per-user content
  fingerprint (SHA-256 of the file / YouTube video id) blocks duplicates; stage outputs go
  to fixed paths and one media row per kind, so a re-run never duplicates output.
- **Traceability:** `processing_stage_runs` records every stage attempt with start/finish
  times, duration, error code and measured details (input size and duration, FFmpeg time),
  and jobs record queued/started/finished/failed times and attempt counts. This supports
  later latency and reliability evaluation.
- **Playback media:** uploads play from their stored original. URL lectures have no upload,
  so the worker stores one compact private playback file (48 kbps AAC, about 22 MB per
  hour). For lectures processed before this existed, run
  `python -m app.workers.playback <lecture-id>`.
- **YouTube:** only single-video YouTube links are accepted. Availability is checked with
  YouTube's official oEmbed endpoint before a lecture is created. Audio is fetched with
  `yt-dlp`, audio only, anonymously, and with no attempt to bypass sign-in, age, region or
  DRM restrictions. Users must confirm they have the right to use the video.

## Grounded Q&A

```text
question (validated, 3-500 chars) → lecture ownership + READY + same embedding model as the index
  → query embedding (fastembed, bge-small-en-v1.5, 384-dim, in a worker thread)
  → match_lecture_chunks as the user (this lecture only; RLS applies)
  → keep chunks with similarity ≥ RAG_MIN_SIMILARITY, within RAG_CONTEXT_TOKENS
      none left → "I couldn't find enough information in this lecture to answer that
                  reliably." (no LLM call)
  → LLM with numbered, timestamped passages in <evidence>, marked as untrusted data
  → JSON {answerable, answer, citations}; citations must name retrieved passages,
    otherwise the answer is discarded as insufficient evidence
  → answer + cited sources (chunk, timestamps, passage text) → chat_logs
```

- **Threshold.** Measured on the CS229 lecture (12 questions the lecture covers, 12 it
  doesn't), top-chunk similarity was 0.665–0.803 for covered questions and 0.383–0.663 for
  the others. The ranges almost meet, so 0.6 is a first filter that turns away clearly
  unrelated questions without an LLM call. Borderline questions (for example related ML
  topics the lecture doesn't teach) are declined by the model. This is a calibration
  note, not an evaluation result.
- **What is stored.** Every answered or declined question is stored with the answer,
  every candidate chunk and its similarity, the chunks used and cited, the
  threshold/top-k/budget, the embedding model, LLM provider/model, prompt version, and
  retrieval, LLM and total latency. This is enough to compute retrieval and answer metrics
  later. Provider errors are not stored, because nothing was answered.
- Retrieval reduces unsupported answers; it doesn't eliminate them. The model can still
  misread a cited passage.

## Search and history

- **Metadata search** is the lecture list's `q` filter: case-insensitive matching of title,
  subject, topic, instructor and tags in Postgres. It's always limited to the caller's lectures.
- **Semantic search** embeds the query with the same model as the lecture chunks (no LLM)
  and calls `search_lecture_content` as the user. That database function ranks only the
  caller's READY lectures' chunks made with the same embedding model, exactly by cosine
  distance, so other users' vectors are never scanned. Results keep a similarity of at
  least `SEARCH_MIN_SIMILARITY`, at most `SEARCH_MAX_PER_LECTURE` per lecture. Each one shows
  the lecture, the chunk's own start and end time, and the passage. Opening a result goes
  to `/lectures/{id}?t=…`, which positions the player and transcript there without
  autoplay. Measured on two CS229 lectures (148 chunks), a content search takes about
  0.3 s and a metadata search about 0.1 s. The first content search after the API starts
  also loads the embedding model.
- **History** comes from `chat_logs`: every question with its answer or
  insufficient-evidence outcome, its cited passages and timestamps, and its lecture.
  "Open in lecture" goes to `/lectures/{id}?question=…&t=…`, which reopens that answer at
  its first source.
- **Deleting a lecture** deletes its question history in the database (foreign-key
  cascade), not just hides it; other history is unaffected. Deleting questions only removes
  the caller's own rows, after an ownership check on the server.

## Security model

- Supabase Auth is the only identity provider. The backend verifies every token (signature
  via JWKS or legacy secret, issuer, audience, role, expiry, with 30 s clock-skew leeway).
- User-facing reads go to Supabase with the caller's own token, so RLS applies. Ingestion
  writes use the service role only after ownership comes from the verified token; user
  ids are never taken from requests.
- RLS is on for every table. Clients can read only their own lectures, jobs, stage runs
  and media. Only the server writes processing records. Worker functions (claim, renew,
  recover) are callable only by the service role.
- Uploads are identified from their bytes (magic numbers), not the browser's claimed type
  or filename. Storage paths are server-chosen (`{user}/{lecture}/original/source.<ext>`),
  so user filenames never reach the filesystem or storage paths. FFmpeg/ffprobe run with
  argument lists (no shell) and timeouts, in a private per-run temp directory that is
  always removed.
- The `lectures` bucket is private; objects are reachable only by their owner.
- Transcripts, chunks, embeddings, chapters and intelligence are readable only by the
  lecture's owner (RLS) and writable only by the service role. `match_lecture_chunks`
  runs with the caller's rights (SECURITY INVOKER), so retrieval can't cross users.
- Workspace, media and question endpoints load the lecture with the caller's token and id
  first. Another user's lecture is a 404, and nothing else is read. Media is reachable
  only through short-lived signed URLs that storage policies let only the owner create.
- `chat_logs` is readable only by its owner (for lectures they still own) and written only
  by the server after the ownership check; clients can't insert, edit or delete history
  directly. Question deletes go through the API, which checks ownership first.
- Search and history take the user only from the verified token. Changing a lecture or
  question id in a request returns nothing or a 404, never another user's data.
- Retrieved transcript text and the question are data in separate prompt sections.
  Angle brackets are neutralized so they can't close or open a section, and sources
  come from the application's own retrieval, never from model output.

## Operations

- **Health:** `GET /health` is liveness (no dependencies). `GET /health/ready` checks the
  database (503 if unreachable) and reports Redis and live workers (`degraded` if either is
  missing; uploads still work and the database sweep catches up). It returns only booleans
  and counts.
- **Rate limits** (per user, fixed window in Redis, `RATE_LIMIT_*`): questions 20 per 5 min,
  passage search 60 per min, uploads and YouTube ingestion 10 per hour each. Over the limit
  the API returns 429 with `Retry-After`. If Redis is down, requests are allowed and a
  warning is logged.
- **Logs:** one line per request with a correlation id (`X-Request-ID`, echoed in responses),
  method, route template, status and duration. Worker lines carry the job id, with
  `stage_finished ... duration_ms=... error_code=...` for every stage. Query strings, request
  bodies, tokens and lecture or question text are never logged. Supabase error bodies are
  reduced to their code and message, because PostgREST puts failing row contents in
  `details`. `LOG_FORMAT=json` emits JSON lines.
- **Workers:** each worker refreshes a presence key in Redis, which expires after
  `WORKER_PRESENCE_TTL_SECONDS`. The recovery sweep logs `stuck_job` warnings for jobs due
  but not started for `STUCK_QUEUED_SECONDS`, or running longer than `STUCK_RUNNING_SECONDS`.
  A job whose worker dies after it has used all its attempts is now failed (retryable by
  its owner) instead of being re-queued forever. Stale job workspaces are removed at
  start-up and periodically.
- **Orphaned media:** `python -m app.workers.maintenance orphans` lists stored objects whose
  lecture no longer exists, or that no media row references, and that are older than 24 h.
  It is a dry run unless `--apply` is given.
- **Redis in deployment:** Redis must not be reachable from the internet. Bind it to a
  private interface or localhost, require a password (`requirepass`, or ACLs on Redis 6+)
  and put it in `REDIS_URL` (`redis://:password@host:6379/0`); use TLS (`rediss://`) across
  networks. The Windows development service listens on all interfaces without a password
  until reconfigured (see Known limitations).
- **Backups (not configured):** this project has **no verified backup**. Supabase's
  automatic backups depend on the plan; check *Database → Backups* in the dashboard rather
  than assuming they exist. Manual procedure:
  `npx supabase db dump -f schema.sql`, `npx supabase db dump --data-only -f data.sql`
  (add `--role-only` for roles). Storage objects (lecture media) are *not* included and must
  be copied separately. Restore into a scratch project with `psql` to test the dump before
  relying on it.

## Research evaluation (`backend/evaluation/`)

Offline tooling for the thesis. It reuses the production retrieval and answer code
(`app.services.rag`), and writes runs to `backend/evaluation/runs/` (git-ignored), never
to production tables. Usage: `python -m evaluation.cli --help` from `backend/`.

- **Datasets** (`evaluation/dataset.py`, format in `evaluation/examples/example_dataset.json`,
  which is clearly marked EXAMPLE):
  - human-written questions, answerable (with gold spans and a reference answer) or
    deliberately unanswerable, with annotation provenance and agreement fields;
  - `split` is calibration, dev or test. Test data runs only when frozen, and parameter
    sweeps are refused on it, so threshold tuning can't leak into the test set;
  - the earlier 24-question threshold calibration was ad hoc and is not part of any dataset.
- **Separation:** evaluation lectures must belong to the `EVAL_USER_ID` account, be READY
  and be embedded with the configured model; anything else is refused.
- **Runs record:**
  - git commit and dirty flag, dataset id, version and content hash;
  - retrieval settings and abstention stages, with whitelisted `--set` overrides;
  - embedding model, generator model, temperature and prompt hash;
  - the ASR and chunking configuration each lecture was actually processed with;
  - a config hash.
  `rerun-check` repeats retrieval and reports any difference.
- **Metrics:**
  - Hit@K, Recall@K, MRR and timestamp hit against gold spans (±30 s default tolerance);
  - WER and CER with a fixed, versioned normalizer;
  - abstention precision and recall, false-refusal rate;
  - citation coverage, kept separate from human-labelled citation support (full / partial / none);
  - answer correctness from human labels, with an optional secondary LLM judge that must
    differ from the generator; reported separately;
  - Cohen's kappa;
  - latency summaries.
  `timings` exports stored stage and Q&A timings (numbers only).
- **Literature comparison:** `evaluation/literature/comparison.json` records each paper's
  published results unchanged, with a comparability label (directly comparable,
  limited/conditional, not directly comparable) and the reason. LectureMind fields stay
  empty until measured.

## Known limitations

- Access tokens stay valid until they expire (default 1 hour) even after logout; the
  refresh token is revoked immediately.
- The Windows Redis port (3.0.504) is old and has no authentication or protected mode by
  default. Bind it to localhost (`bind 127.0.0.1` in `redis.windows-service.conf`) or use a
  password-protected Redis for anything beyond local development.
- YouTube may block anonymous downloads; such lectures fail with a clear, non-fake reason.
- Transcription runs on CPU (about 0.2x real time for the `small` model on a 14-thread
  laptop CPU, so roughly 15 minutes per hour of lecture).
- On Groq's free tier (8,000 tokens per minute, counting prompt plus `max_tokens`),
  generation for a long lecture spends most of its time waiting out rate limits (about 5
  minutes for a 75-minute lecture). With `LLM_MAX_OUTPUT_TOKENS=2500`, the final synthesis
  can reach the output cap. The notes stay valid and grounded but may be shorter, and this
  is recorded as `finish_reason: length` in `lecture_intelligence.generation`. A paid tier
  or a larger cap removes it.
- Q&A waits out at most one provider rate limit (`RAG_RATE_LIMIT_RETRIES`) and otherwise
  returns a retryable "answer couldn't be generated" error.
- Rate limits are per user only (no per-IP limit for unauthenticated traffic); they fail
  open while Redis is down.
- Dependency audit (Phase 7B): `pip-audit` found no known vulnerabilities in the backend
  environment. `npm audit` reports a moderate advisory in `react-router-dom` 6.x (an open
  redirect via backslash paths; the fix needs v7). The app's only dynamic redirect is
  validated by `safeAppPath`. Dev-only tooling (vite 5, vitest 2, esbuild) has advisories
  whose fixes are major upgrades; these affect the development server, not the built
  bundle. The upgrades are deferred.
- The first question after the API starts loads the embedding model (about a second).

## Tech stack

- **Frontend:** React + JavaScript (no TypeScript), React Router, Vite, `@supabase/supabase-js`
- **Backend:** FastAPI + Python, PyJWT, httpx, redis-py, FFmpeg/ffprobe, yt-dlp
- **Platform:** Supabase Auth, PostgreSQL, Storage; Redis
- **Intelligence:** faster-whisper (CTranslate2), fastembed (ONNX Runtime), pgvector, an
  OpenAI-compatible LLM provider. No PyTorch.
