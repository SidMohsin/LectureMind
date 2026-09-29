# LectureMind

LectureMind is a Lecture Intelligence Platform that converts recorded lectures into a
structured, searchable, lecture-grounded knowledge asset: timestamped transcript,
chapters, key concepts, definitions, and grounded question answering with source
timestamps.

Full product/technical source of truth: the PRD, Architecture, Design, Roadmap, Memory
and Testing documents supplied with this project.

## Current status: Phase 1 — Foundation + Platform Setup

This repository currently contains the **application foundation only**:

- a React + JavaScript frontend with routing, a shared design system, an application
  shell, and route boundaries for every planned page
- a FastAPI backend with configuration, error handling, CORS, and a health endpoint

Authentication, lecture ingestion, transcription, embeddings, RAG, search and history
are **not implemented yet** — those are built in later roadmap phases. Pages for those
features currently render a clearly labeled placeholder instead of fake functionality.

## Project structure

```text
frontend/   React + JavaScript application (Vite, React Router)
backend/    FastAPI application
```

## Frontend setup

```bash
cd frontend
npm install
cp .env.example .env   # set VITE_API_BASE_URL if the backend isn't on localhost:8000
npm run dev
```

The app runs at http://localhost:5173 (Vite will pick the next free port if that one is
taken).

### Frontend environment variables

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Base URL of the FastAPI backend used by the central API client (`src/services/api.js`). |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | Reserved for Phase 2 authentication. Not used yet. |

## Backend setup

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

The API runs at http://localhost:8000.

### Backend environment variables

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `development` / `staging` / `production`. |
| `APP_NAME` | Display name returned by `/health`. |
| `LOG_LEVEL` | Root logger level. |
| `CORS_ALLOW_ORIGINS` | Comma-separated list of origins allowed to call the API. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Reserved for Phase 2 (Auth + Storage). Not used yet. |
| `DATABASE_URL` | Reserved for Phase 2 (PostgreSQL + pgvector). Not used yet. |
| `REDIS_URL` | Reserved for Phase 4 (async processing queue). Not used yet. |
| `LLM_PROVIDER`, `LLM_API_KEY` | Reserved for Phase 6 (grounded Q&A). Not used yet. |

## Health check

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"LectureMind API","environment":"development"}
```

## Phase 1 scope

Implemented:

- Frontend and backend project structure per the architecture document
- React Router routes/placeholders for every planned page
- Shared authenticated application shell (navbar, footer) matching the approved screenshots
- Reusable design tokens and UI primitives (Button, Input, Badge, Card, EmptyState)
- Central frontend API client (`src/services/api.js`)
- FastAPI app with configuration, structured logging, CORS, and centralized error handling
- `GET /health`
- Environment-based configuration for both apps, with `.env.example` files and no
  committed secrets

Explicitly **not** implemented in Phase 1 (see the Roadmap for when each lands):
Supabase Auth, lecture upload/ingestion, YouTube ingestion, FFmpeg, Whisper,
transcription, chunking, embeddings, pgvector, RAG/LLM integration, summaries,
chapters, concepts, search, question history, background workers, Redis job
processing, production deployment, and evaluation.

## Tech stack

- **Frontend:** React + JavaScript (no TypeScript), React Router, Vite
- **Backend:** FastAPI + Python
- **Planned (later phases):** Supabase Auth, Supabase PostgreSQL + pgvector, Supabase
  Storage, Redis + background workers, FFmpeg, Whisper/faster-whisper, sentence
  embeddings, an LLM provider abstraction
