# LectureMind

LectureMind is a Lecture Intelligence Platform that converts recorded lectures into a
structured, searchable, lecture-grounded knowledge asset: timestamped transcript,
chapters, key concepts, definitions, and grounded question answering with source
timestamps.

Full product/technical source of truth: the PRD, Architecture, Design, Roadmap, Memory
and Testing documents supplied with this project.

## Current status: Phase 2 — Authentication + Data Infrastructure

Implemented so far:

- **Phase 1:** React + JavaScript frontend (Vite, React Router, design tokens, app shell,
  central API client) and FastAPI backend (config, logging, error handling, `/health`).
- **Phase 2:** Supabase Auth (sign up, email verification, login, session restore,
  logout, forgot/reset password), protected routes, a reusable backend auth dependency,
  the `profiles` and `lectures` ownership schema with Row Level Security, and a private
  `lectures` storage bucket with per-user, per-lecture access policies.

Not implemented yet (later phases): lecture upload/ingestion, YouTube ingestion,
processing workers, FFmpeg, Whisper, transcripts, embeddings/pgvector, intelligence,
RAG/Q&A, search, question history, deployment and evaluation. Pages for those features
show a clearly labeled placeholder.

## Project structure

```text
frontend/            React + JavaScript application (Vite, React Router)
backend/             FastAPI application
  app/api/           Routers (health, me) and shared dependencies (deps.py)
  app/core/          Config, token verification, errors, logging
  app/services/      User-scoped Supabase data access
  app/repositories/  Table-level queries
  tests/             Offline unit tests; tests/integration = live Supabase suite
supabase/
  config.toml        Supabase CLI project config (auth settings mirror the hosted project)
  migrations/        Reproducible schema, RLS and storage policies
```

## 1. Supabase project setup

Use a separate Supabase project per environment (development / staging / production).

1. **Create a project** at supabase.com.
2. **Apply the schema** from `supabase/migrations/` with the Supabase CLI (runs via `npx`,
   no global install or Docker needed):

   ```bash
   npx supabase login
   npx supabase link --project-ref <project-ref>
   npx supabase db push
   ```

   This creates `public.profiles`, `public.lectures`, their RLS policies, the profile
   trigger, and the private `lectures` storage bucket with its policies. Never change the
   schema by hand in the dashboard; add a new migration instead
   (`npx supabase migration new <name>`).
3. **Configure Auth** (Dashboard → Authentication):
   - *URL Configuration*: Site URL `http://localhost:5173`; Redirect URLs
     `http://localhost:5173/verify` and `http://localhost:5173/reset-password`.
   - *Sign In / Providers → Email*: Email enabled, **Confirm email on**, minimum password
     length **8**.

   These match `[auth]` in `supabase/config.toml`.
4. **Email delivery.** Supabase's built-in email service only delivers to members of your
   Supabase organisation and is heavily rate-limited. That is fine for development with
   your own address. Configure custom SMTP (Authentication → Emails → SMTP Settings)
   before anyone else signs up.
5. **Copy the keys** from Project Settings → API Keys into the `.env` files below. Only the
   project URL and the anon/publishable key are needed by the app.

## 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev          # http://localhost:5173
npm test             # unit/component tests (Vitest)
npm run lint
npm run build
```

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | FastAPI base URL used by the central API client (`src/services/api.js`). |
| `VITE_SUPABASE_URL` | Supabase project URL. |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon / publishable key (public). Never put the service-role key in a `VITE_` variable. |

Without the two Supabase values the app shows a configuration screen instead of starting.

## 3. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS/Linux
pip install -r requirements-dev.txt   # requirements.txt + pytest
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `development` / `staging` / `production`. |
| `APP_NAME`, `LOG_LEVEL` | Service name reported by `/health`; root log level. |
| `CORS_ALLOW_ORIGINS` | Comma-separated origins allowed to call the API. |
| `SUPABASE_URL` | Supabase project URL. Also defines the expected token issuer and JWKS location. |
| `SUPABASE_ANON_KEY` | Anon / publishable key, sent as `apikey` on user-scoped data requests. |
| `SUPABASE_JWT_SECRET` | Only for projects still using the legacy shared HS256 JWT secret. Leave empty for projects on JWT signing keys (verified via JWKS). |

The backend does **not** use the service-role key. Later phases (workers) will add
`DATABASE_URL`, `REDIS_URL` and LLM settings; they are listed commented-out in
`.env.example`.

### Endpoints

| Endpoint | Auth | Description |
|---|---|---|
| `GET /health` | public | `{"status":"ok","service":"LectureMind API","environment":"development"}` |
| `GET /me` | bearer token | The caller's identity and profile (`id`, `email`, `display_name`, `created_at`). |

### Tests

```bash
pytest                       # offline unit tests (token verification, /me, error mapping, CORS)
pytest -m integration        # live Supabase security suite (auth flows, RLS, storage)
```

The live suite needs `backend/.env.test` (copy `.env.test.example`). It uses a
**development** project and its service-role key, only to create, confirm and delete
throwaway `lecturemind-test-*@example.com` users. The application never reads that file.

## Security model

- **Identity:** Supabase Auth is the only identity provider. The frontend keeps the
  session with `@supabase/supabase-js`. The central API client sends the access token as
  `Authorization: Bearer …`.
- **Backend authentication:** `get_current_user` (`app/api/deps.py`) verifies every token
  locally. It checks the signature (JWKS for asymmetric keys, or the legacy HS256 secret
  when configured), issuer, `authenticated` audience and role, and expiry. Missing or
  invalid tokens get `401`.
- **Authorization:** the backend never trusts IDs from the client. Queries go to Supabase
  with the caller's own token, so RLS applies to backend reads exactly as it does to
  direct client access. Repositories also filter by the token's user id.
- **Database:** RLS is on for every table. `lectures.user_id` defaults to `auth.uid()`
  and clients have no privilege on that column, or on system-managed `status` and
  `duration_seconds`. Clients cannot create, change or reassign ownership. `profiles` is
  read-only for clients and created by a trigger on sign-up.
- **Storage:** the `lectures` bucket is private and limited to audio/video MIME types.
  Objects live at `{user_id}/{lecture_id}/{original|processed|derived}/…`. A user can
  read or write only under their own folder and inside a lecture they own.
- **Known limitation:** access tokens are stateless JWTs. After logout the refresh token
  is revoked immediately, but an already-issued access token stays valid until it
  expires (default 1 hour).

## Tech stack

- **Frontend:** React + JavaScript (no TypeScript), React Router, Vite, `@supabase/supabase-js`
- **Backend:** FastAPI + Python, PyJWT, httpx
- **Platform:** Supabase Auth, Supabase PostgreSQL, Supabase Storage
- **Planned (later phases):** pgvector, Redis + background workers, FFmpeg,
  Whisper/faster-whisper, sentence embeddings, an LLM provider abstraction
