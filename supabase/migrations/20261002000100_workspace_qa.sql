-- Phase 6: lecture workspace + grounded Q&A.
--
-- 1. lecture_media gains a 'playback' kind: a compact private audio rendition the
--    worker stores for lectures whose source isn't a user upload (e.g. a YouTube URL),
--    so they can be played in the workspace through signed URLs like uploads.
-- 2. chat_logs stores every lecture-specific question with its answer (or the
--    insufficient-evidence outcome), the exact evidence it was based on, the
--    retrieval configuration and timings, so answers can be audited and evaluated.

alter table public.lecture_media drop constraint lecture_media_kind_check;
alter table public.lecture_media
  add constraint lecture_media_kind_check check (kind in ('original', 'audio', 'playback'));

create table public.chat_logs (
  id uuid primary key default gen_random_uuid(),
  lecture_id uuid not null references public.lectures (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  question text not null check (char_length(question) between 1 and 1000),
  -- 'answered': grounded answer with at least one cited source.
  -- 'insufficient_evidence': retrieval or the model found no adequate support; no answer is presented.
  outcome text not null check (outcome in ('answered', 'insufficient_evidence')),
  answer text not null check (char_length(answer) <= 8000),
  -- Ordered list of {chunk_id, sequence, start_seconds, end_seconds, similarity, text, cited}.
  sources jsonb not null default '[]'::jsonb check (jsonb_typeof(sources) = 'array'),
  -- Retrieval configuration and every candidate considered: {top_k, min_similarity, candidates: [...]}.
  retrieval jsonb not null default '{}'::jsonb,
  embedding_model text not null,
  llm_provider text,
  llm_model text,
  prompt_version text,
  retrieval_ms integer check (retrieval_ms is null or retrieval_ms >= 0),
  llm_ms integer check (llm_ms is null or llm_ms >= 0),
  latency_ms integer not null check (latency_ms >= 0),
  created_at timestamptz not null default now()
);

create index chat_logs_lecture_created_idx on public.chat_logs (lecture_id, created_at desc);
create index chat_logs_user_created_idx on public.chat_logs (user_id, created_at desc);

alter table public.chat_logs enable row level security;

revoke all on table public.chat_logs from anon, authenticated;
grant select on table public.chat_logs to authenticated;
grant all on table public.chat_logs to service_role;

-- Owners read their own history for lectures they still own. Only the server writes,
-- after it has verified ownership and produced the answer.
create policy "chat_logs_select_own"
  on public.chat_logs for select to authenticated
  using ((select auth.uid()) = user_id and public.owns_lecture(lecture_id));
