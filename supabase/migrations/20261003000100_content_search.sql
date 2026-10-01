-- Phase 7A: semantic content search across the caller's own lectures.
--
-- SECURITY INVOKER: it runs with the caller's rights, so Row Level Security on
-- lectures and lecture_chunks applies, and it additionally filters to
-- auth.uid()'s lectures explicitly. Only READY lectures whose chunks were embedded
-- with the same model as the query are searched (vectors from different models
-- are never compared).
--
-- The caller's chunks are selected first and ranked exactly by cosine distance:
-- per-user corpora are small, results are exact, and other users' vectors are never
-- part of the scan. (Per-lecture Q&A keeps using match_lecture_chunks / HNSW.)

create or replace function public.search_lecture_content(
  p_query_embedding extensions.vector(384),
  p_embedding_model text,
  p_match_count integer default 30
)
returns table (
  chunk_id uuid,
  lecture_id uuid,
  lecture_title text,
  lecture_subject text,
  lecture_topic text,
  lecture_instructor text,
  lecture_date date,
  sequence integer,
  text text,
  start_seconds double precision,
  end_seconds double precision,
  similarity double precision
)
language sql
stable
security invoker
set search_path = ''
as $$
  with mine as materialized (
    select c.id, c.lecture_id, l.title, l.subject, l.topic, l.instructor, l.lecture_date,
           c.sequence, c.text, c.start_seconds, c.end_seconds, c.embedding
    from public.lecture_chunks c
    join public.lectures l on l.id = c.lecture_id
    where l.user_id = (select auth.uid())
      and l.status = 'READY'
      and c.embedding is not null
      and c.embedding_model = p_embedding_model
  )
  select m.id, m.lecture_id, m.title, m.subject, m.topic, m.instructor, m.lecture_date,
         m.sequence, m.text, m.start_seconds::double precision, m.end_seconds::double precision,
         (1 - (m.embedding operator(extensions.<=>) p_query_embedding))::double precision as similarity
  from mine m
  order by m.embedding operator(extensions.<=>) p_query_embedding
  limit least(greatest(coalesce(p_match_count, 30), 1), 100);
$$;

revoke execute on function public.search_lecture_content(extensions.vector, text, integer) from public, anon;
grant execute on function public.search_lecture_content(extensions.vector, text, integer) to authenticated, service_role;
