# LectureMind

LectureMind is a Lecture Intelligence Platform that converts recorded lectures into a
structured, searchable, lecture-grounded knowledge asset: timestamped transcript,
chapters, key concepts, definitions, and grounded question answering with source
timestamps.

Full product/technical source of truth: the PRD, Architecture, Design, Roadmap, Memory
and Testing documents supplied with this project.

## Current status: Phase 4 — Lecture Ingestion + Processing

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

**Phase boundary.** Phase 4 implements the `EXTRACTING_AUDIO` stage. Transcription and
everything after it are Phase 5. When a lecture reaches a stage that isn't implemented
yet, its job **waits** there, labelled "Transcription isn't available yet". It is never
marked READY and no stage output is faked. When Phase 5 registers the next stage
(`STAGE_HANDLERS` in `backend/app/workers/pipeline.py`), waiting jobs resume from that
stage automatically.

Not implemented yet: Whisper transcription, transcripts, chunking, embeddings/pgvector,
lecture intelligence, the lecture workspace, grounded Q&A, search, question history,
deployment and evaluation.

## Project structure

```text
frontend/              React + JavaScript application (Vite, React Router)
backend/               FastAPI application + processing worker
  app/api/             Routers (health, me, lectures, ingestion) and auth dependencies
  app/core/            Config, token verification, errors, logging
  app/services/        Supabase access (user-scoped + service role), ingestion,
                       Redis queue, source-URL providers
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
| `REDIS_URL` | Queue server (default `redis://localhost:6379/0`). |
| `WORK_DIR` | Scratch space for per-job files (default: system temp). |
| `FFMPEG_PATH`, `FFPROBE_PATH` | Binaries (default: from `PATH`). |
| `MAX_VIDEO_BYTES`, `MAX_AUDIO_BYTES`, `MAX_MEDIA_DURATION_SECONDS` | Authoritative ingestion limits. |
| `SOURCE_URL_DOWNLOADS_ENABLED` | Allow YouTube URL ingestion. |
| `WORKER_*` | Lease, heartbeat, recovery-sweep and retry-backoff timings. |

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

### Tests

```bash
pytest                   # offline: API, lifecycle, pipeline, worker (real FFmpeg), queue
pytest -m integration    # live: Supabase auth/RLS/storage, ingestion + worker end to end, Redis
```

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
    → FFmpeg → 16 kHz mono FLAC → processed/audio.flac (fixed path, upsert)
  → next stage (TRANSCRIBING, Phase 5) → job waits until it exists
```

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
- **YouTube:** only single-video YouTube links are accepted. Availability is checked with
  YouTube's official oEmbed endpoint before a lecture is created. Audio is fetched with
  `yt-dlp`, audio only, anonymously, and with no attempt to bypass sign-in, age, region or
  DRM restrictions. Users must confirm they have the right to use the video.

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

## Known limitations

- Access tokens stay valid until they expire (default 1 hour) even after logout; the
  refresh token is revoked immediately.
- The Windows Redis port (3.0.504) is old and has no authentication or protected mode by
  default. Bind it to localhost (`bind 127.0.0.1` in `redis.windows-service.conf`) or use a
  password-protected Redis for anything beyond local development.
- YouTube may block anonymous downloads; such lectures fail with a clear, non-fake reason.

## Tech stack

- **Frontend:** React + JavaScript (no TypeScript), React Router, Vite, `@supabase/supabase-js`
- **Backend:** FastAPI + Python, PyJWT, httpx, redis-py, FFmpeg/ffprobe, yt-dlp
- **Platform:** Supabase Auth, PostgreSQL, Storage; Redis
- **Planned:** Whisper/faster-whisper, sentence embeddings, pgvector retrieval, an LLM
  provider abstraction
