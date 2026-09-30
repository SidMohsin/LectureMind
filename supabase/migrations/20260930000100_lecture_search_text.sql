-- Metadata search for the lecture library: one lower-cased, generated column
-- covering title, subject, topic, instructor and tags, queried with ILIKE.

create or replace function public.lecture_tags_text(tags text[])
returns text
language sql
immutable
parallel safe
set search_path = ''
as $$
  select coalesce(array_to_string(tags, ' '), '');
$$;

alter table public.lectures
  add column search_text text generated always as (
    lower(
      title || ' ' || coalesce(subject, '') || ' ' || coalesce(topic, '') || ' '
      || coalesce(instructor, '') || ' ' || public.lecture_tags_text(tags)
    )
  ) stored;
