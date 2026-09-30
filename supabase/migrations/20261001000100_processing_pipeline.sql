-- Phase 4: lecture ingestion + asynchronous processing.
--
-- Postgres is the source of truth for processing state; Redis only carries
-- "job X is ready" notifications. All writes to these tables happen
-- server-side (API / worker with the service role). Clients can read only
-- the rows that belong to their own lectures.

-- ---------------------------------------------------------------------------
-- Lectures: provenance + duplicate protection
-- ---------------------------------------------------------------------------

alter table public.lectures
  add column original_filename text check (original_filename is null or char_length(original_filename) <= 255),
  -- "sha256:<hex>" of an uploaded file or "youtube:<video id>" for a source URL.
  add column source_fingerprint text check (source_fingerprint is null or char_length(source_fingerprint) <= 200),
  -- Client-generated key for one submission, so a retried request can't create a second lecture.
  add column client_request_id uuid,
  add column source_rights_confirmed_at timestamptz;

create unique index lectures_user_request_unique on public.lectures (user_id, client_request_id)
  where client_request_id is not null;
create unique index lectures_user_fingerprint_unique on public.lectures (user_id, source_fingerprint)
  where source_fingerprint is not null;

-- ---------------------------------------------------------------------------
-- Media stored for a lecture (original upload, normalized audio)
-- ---------------------------------------------------------------------------

create table public.lecture_media (
  id uuid primary key default gen_random_uuid(),
  lecture_id uuid not null references public.lectures (id) on delete cascade,
  kind text not null check (kind in ('original', 'audio')),
  storage_path text not null,
  mime_type text not null,
  file_size bigint not null check (file_size >= 0),
  checksum_sha256 text check (checksum_sha256 is null or checksum_sha256 ~ '^[0-9a-f]{64}$'),
  duration_seconds numeric(10, 3) check (duration_seconds is null or duration_seconds >= 0),
  -- Selected ffprobe facts (container, codecs, sample rate, channels) for traceability.
  probe jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (lecture_id, kind)
);

create trigger lecture_media_set_updated_at
  before update on public.lecture_media
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Processing jobs: exactly one per lecture, reused across retries
-- ---------------------------------------------------------------------------

create table public.processing_jobs (
  id uuid primary key default gen_random_uuid(),
  lecture_id uuid not null unique references public.lectures (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  -- queued: waiting for a worker; running: leased by a worker;
  -- waiting: the next stage has no implementation yet (resumes when it does);
  -- succeeded / failed: terminal until a retry.
  status text not null default 'queued' check (status in ('queued', 'running', 'waiting', 'succeeded', 'failed')),
  current_stage text not null default 'EXTRACTING_AUDIO' check (
    current_stage in (
      'EXTRACTING_AUDIO', 'TRANSCRIBING', 'CLEANING', 'CHUNKING', 'EMBEDDING', 'INDEXING', 'GENERATING_INTELLIGENCE'
    )
  ),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 3 check (max_attempts >= 1),
  -- Earliest time a queued job may run (automatic retry backoff).
  next_attempt_at timestamptz not null default now(),
  lease_owner text,
  lease_expires_at timestamptz,
  error_code text,
  error_message text check (error_message is null or char_length(error_message) <= 1000),
  retryable boolean,
  status_detail text check (status_detail is null or char_length(status_detail) <= 300),
  queued_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  failed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint processing_jobs_running_has_lease check (status <> 'running' or (lease_owner is not null and lease_expires_at is not null))
);

create index processing_jobs_status_idx on public.processing_jobs (status, next_attempt_at);
create index processing_jobs_user_idx on public.processing_jobs (user_id);

create trigger processing_jobs_set_updated_at
  before update on public.processing_jobs
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Per-stage attempt log: timings for latency / reliability evaluation
-- ---------------------------------------------------------------------------

create table public.processing_stage_runs (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.processing_jobs (id) on delete cascade,
  stage text not null,
  attempt integer not null check (attempt >= 1),
  status text not null default 'running' check (status in ('running', 'succeeded', 'failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  duration_ms integer check (duration_ms is null or duration_ms >= 0),
  error_code text,
  details jsonb not null default '{}'::jsonb,
  unique (job_id, stage, attempt)
);

-- ---------------------------------------------------------------------------
-- Access: clients read their own rows; only the service role writes
-- ---------------------------------------------------------------------------

alter table public.lecture_media enable row level security;
alter table public.processing_jobs enable row level security;
alter table public.processing_stage_runs enable row level security;

revoke all on table public.lecture_media, public.processing_jobs, public.processing_stage_runs from anon, authenticated;
grant select on table public.lecture_media, public.processing_jobs, public.processing_stage_runs to authenticated;
grant all on table public.lecture_media, public.processing_jobs, public.processing_stage_runs to service_role;

create policy "lecture_media_select_own"
  on public.lecture_media for select to authenticated
  using (exists (select 1 from public.lectures l where l.id = lecture_id and l.user_id = (select auth.uid())));

create policy "processing_jobs_select_own"
  on public.processing_jobs for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "processing_stage_runs_select_own"
  on public.processing_stage_runs for select to authenticated
  using (exists (select 1 from public.processing_jobs j where j.id = job_id and j.user_id = (select auth.uid())));

-- ---------------------------------------------------------------------------
-- Worker coordination (service role only). Uses database time so worker
-- clock skew can't break leases.
-- ---------------------------------------------------------------------------

-- Atomically lease a job that is due. Returns nothing if another worker holds
-- it, it isn't due yet, or it is in any other state.
create or replace function public.claim_processing_job(p_job_id uuid, p_worker text, p_lease_seconds integer)
returns setof public.processing_jobs
language sql
security definer
set search_path = ''
as $$
  update public.processing_jobs
     set status = 'running',
         lease_owner = p_worker,
         lease_expires_at = now() + make_interval(secs => p_lease_seconds),
         attempt_count = attempt_count + 1,
         started_at = coalesce(started_at, now()),
         status_detail = null
   where id = p_job_id
     and status = 'queued'
     and next_attempt_at <= now()
  returning *;
$$;

create or replace function public.renew_processing_lease(p_job_id uuid, p_worker text, p_lease_seconds integer)
returns boolean
language sql
security definer
set search_path = ''
as $$
  with renewed as (
    update public.processing_jobs
       set lease_expires_at = now() + make_interval(secs => p_lease_seconds)
     where id = p_job_id and status = 'running' and lease_owner = p_worker
    returning 1
  )
  select exists (select 1 from renewed);
$$;

-- Jobs whose worker vanished (expired lease) go back to the queue; returns the
-- ids of every queued job that is due, so the worker can re-notify Redis.
create or replace function public.recover_processing_jobs(p_limit integer default 50)
returns table (job_id uuid)
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.processing_jobs
     set status = 'queued',
         lease_owner = null,
         lease_expires_at = null,
         status_detail = 'Resumed after an interrupted run.'
   where status = 'running' and lease_expires_at < now();

  return query
    select j.id from public.processing_jobs j
     where j.status = 'queued' and j.next_attempt_at <= now()
     order by j.next_attempt_at
     limit p_limit;
end;
$$;

revoke execute on function public.claim_processing_job(uuid, text, integer) from public, anon, authenticated;
revoke execute on function public.renew_processing_lease(uuid, text, integer) from public, anon, authenticated;
revoke execute on function public.recover_processing_jobs(integer) from public, anon, authenticated;
grant execute on function public.claim_processing_job(uuid, text, integer) to service_role;
grant execute on function public.renew_processing_lease(uuid, text, integer) to service_role;
grant execute on function public.recover_processing_jobs(integer) to service_role;

-- Normalized audio (16 kHz mono FLAC) is stored alongside the original.
update storage.buckets
   set allowed_mime_types = array[
     'video/mp4', 'video/quicktime', 'video/webm', 'video/x-matroska',
     'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/mp4', 'audio/x-m4a', 'audio/webm', 'audio/ogg', 'audio/flac'
   ]
 where id = 'lectures';
