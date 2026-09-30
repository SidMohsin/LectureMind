-- Lecture ownership foundation. Later phases add media, transcript, chunk,
-- chapter, intelligence, chat and job tables that reference lectures(id).

create table public.lectures (
  id uuid primary key default gen_random_uuid(),
  -- Ownership is always derived from the caller's identity: clients have no
  -- insert/update privilege on this column, so it can only ever be auth.uid().
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  title text not null check (char_length(trim(title)) between 1 and 300),
  subject text check (subject is null or char_length(subject) <= 120),
  topic text check (topic is null or char_length(topic) <= 200),
  instructor text check (instructor is null or char_length(instructor) <= 120),
  lecture_date date,
  tags text[] not null default '{}',
  source_type text not null check (source_type in ('video', 'audio', 'url')),
  source_url text check (source_url is null or char_length(source_url) <= 2048),
  status text not null default 'UPLOADED' check (
    status in (
      'UPLOADED', 'QUEUED', 'EXTRACTING_AUDIO', 'TRANSCRIBING', 'CLEANING', 'CHUNKING',
      'EMBEDDING', 'INDEXING', 'GENERATING_INTELLIGENCE', 'READY', 'FAILED'
    )
  ),
  duration_seconds integer check (duration_seconds is null or duration_seconds >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint lectures_source_url_matches_type check ((source_type = 'url') = (source_url is not null))
);

create index lectures_user_id_created_at_idx on public.lectures (user_id, created_at desc);

create trigger lectures_set_updated_at
  before update on public.lectures
  for each row execute function public.set_updated_at();

alter table public.lectures enable row level security;

-- Column-level privileges: users may create lectures and edit descriptive
-- metadata. user_id, status and duration are system-managed (service role).
revoke all on table public.lectures from anon, authenticated;
grant select, delete on table public.lectures to authenticated;
grant insert (title, subject, topic, instructor, lecture_date, tags, source_type, source_url)
  on table public.lectures to authenticated;
grant update (title, subject, topic, instructor, lecture_date, tags)
  on table public.lectures to authenticated;

create policy "lectures_select_own"
  on public.lectures for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "lectures_insert_own"
  on public.lectures for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "lectures_update_own"
  on public.lectures for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "lectures_delete_own"
  on public.lectures for delete
  to authenticated
  using ((select auth.uid()) = user_id);
