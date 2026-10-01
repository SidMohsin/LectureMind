-- Phase 5: lecture intelligence.
--
-- transcript -> transcript_segments (raw + cleaned, timestamped)
--            -> lecture_chunks (sentence-aware, timestamped, embedded with pgvector)
--            -> chapters + lecture_intelligence (LLM output grounded in chunk references)
--
-- Every row belongs to one lecture; clients can read rows of their own lectures
-- only. All writes happen in the worker with the service role.

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Transcript: one per lecture, with the exact model/configuration used
-- ---------------------------------------------------------------------------

create table public.transcripts (
  lecture_id uuid primary key references public.lectures (id) on delete cascade,
  language text,
  language_probability real,
  audio_duration_seconds numeric(10, 3) not null check (audio_duration_seconds >= 0),
  segment_count integer not null check (segment_count >= 0),
  model text not null,
  model_config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.transcript_segments (
  lecture_id uuid not null references public.lectures (id) on delete cascade,
  sequence integer not null check (sequence >= 0),
  start_seconds numeric(10, 3) not null check (start_seconds >= 0),
  end_seconds numeric(10, 3) not null,
  -- Exactly what the speech model produced (kept for research/debugging).
  raw_text text not null,
  -- After conservative cleaning; empty when the segment was a removed artifact.
  text text,
  avg_logprob real,
  no_speech_prob real,
  primary key (lecture_id, sequence),
  constraint transcript_segments_time_order check (end_seconds >= start_seconds)
);

-- ---------------------------------------------------------------------------
-- Retrieval chunks with embeddings
-- ---------------------------------------------------------------------------

create table public.lecture_chunks (
  id uuid primary key default gen_random_uuid(),
  lecture_id uuid not null references public.lectures (id) on delete cascade,
  sequence integer not null check (sequence >= 0),
  text text not null check (char_length(text) > 0),
  start_seconds numeric(10, 3) not null check (start_seconds >= 0),
  end_seconds numeric(10, 3) not null,
  first_segment integer not null,
  last_segment integer not null,
  token_estimate integer not null check (token_estimate > 0),
  embedding extensions.vector(384),
  embedding_model text,
  created_at timestamptz not null default now(),
  unique (lecture_id, sequence),
  constraint lecture_chunks_time_order check (end_seconds >= start_seconds),
  constraint lecture_chunks_segment_order check (last_segment >= first_segment),
  constraint lecture_chunks_embedding_has_model check ((embedding is null) = (embedding_model is null))
);

create index lecture_chunks_embedding_hnsw
  on public.lecture_chunks using hnsw (embedding extensions.vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- Structured lecture intelligence
-- ---------------------------------------------------------------------------

create table public.chapters (
  lecture_id uuid not null references public.lectures (id) on delete cascade,
  sequence integer not null check (sequence >= 0),
  title text not null check (char_length(title) between 1 and 200),
  description text,
  start_seconds numeric(10, 3) not null check (start_seconds >= 0),
  end_seconds numeric(10, 3) not null,
  first_chunk integer not null,
  last_chunk integer not null,
  primary key (lecture_id, sequence),
  constraint chapters_time_order check (end_seconds >= start_seconds)
);

-- Items in the jsonb arrays carry `chunks` (chunk sequence numbers) as evidence,
-- so later phases can show sources and timestamps.
create table public.lecture_intelligence (
  lecture_id uuid primary key references public.lectures (id) on delete cascade,
  summary text not null,
  topics jsonb not null default '[]'::jsonb,
  key_concepts jsonb not null default '[]'::jsonb,
  definitions jsonb not null default '[]'::jsonb,
  keywords jsonb not null default '[]'::jsonb,
  important_points jsonb not null default '[]'::jsonb,
  examples jsonb not null default '[]'::jsonb,
  provider text not null,
  model text not null,
  prompt_version text not null,
  generation jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Access: read own, server writes
-- ---------------------------------------------------------------------------

alter table public.transcripts enable row level security;
alter table public.transcript_segments enable row level security;
alter table public.lecture_chunks enable row level security;
alter table public.chapters enable row level security;
alter table public.lecture_intelligence enable row level security;

revoke all on table public.transcripts, public.transcript_segments, public.lecture_chunks,
  public.chapters, public.lecture_intelligence from anon, authenticated;
grant select on table public.transcripts, public.transcript_segments, public.lecture_chunks,
  public.chapters, public.lecture_intelligence to authenticated;
grant all on table public.transcripts, public.transcript_segments, public.lecture_chunks,
  public.chapters, public.lecture_intelligence to service_role;

create or replace function public.owns_lecture(p_lecture_id uuid)
returns boolean
language sql
stable
set search_path = ''
as $$
  select exists (
    select 1 from public.lectures l where l.id = p_lecture_id and l.user_id = (select auth.uid())
  );
$$;

revoke execute on function public.owns_lecture(uuid) from public, anon;
grant execute on function public.owns_lecture(uuid) to authenticated;

create policy "transcripts_select_own" on public.transcripts for select to authenticated
  using (public.owns_lecture(lecture_id));
create policy "transcript_segments_select_own" on public.transcript_segments for select to authenticated
  using (public.owns_lecture(lecture_id));
create policy "lecture_chunks_select_own" on public.lecture_chunks for select to authenticated
  using (public.owns_lecture(lecture_id));
create policy "chapters_select_own" on public.chapters for select to authenticated
  using (public.owns_lecture(lecture_id));
create policy "lecture_intelligence_select_own" on public.lecture_intelligence for select to authenticated
  using (public.owns_lecture(lecture_id));

-- ---------------------------------------------------------------------------
-- Retrieval foundation (used by Phase 6). SECURITY INVOKER: when called with a
-- user's token, RLS above limits results to that user's lectures.
-- ---------------------------------------------------------------------------

create or replace function public.match_lecture_chunks(
  p_lecture_id uuid,
  p_query_embedding extensions.vector(384),
  p_match_count integer default 5
)
returns table (
  chunk_id uuid,
  sequence integer,
  text text,
  start_seconds numeric,
  end_seconds numeric,
  similarity double precision
)
language sql
stable
security invoker
set search_path = ''
as $$
  select c.id, c.sequence, c.text, c.start_seconds, c.end_seconds,
         1 - (c.embedding operator(extensions.<=>) p_query_embedding) as similarity
    from public.lecture_chunks c
   where c.lecture_id = p_lecture_id
     and c.embedding is not null
   order by c.embedding operator(extensions.<=>) p_query_embedding
   limit least(greatest(p_match_count, 1), 50);
$$;

revoke execute on function public.match_lecture_chunks(uuid, extensions.vector, integer) from public, anon;
grant execute on function public.match_lecture_chunks(uuid, extensions.vector, integer) to authenticated, service_role;
