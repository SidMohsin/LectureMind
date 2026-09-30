-- Private storage for lecture media.
-- Object path convention: {user_id}/{lecture_id}/{original|processed|derived}/{filename}
-- A user can only touch objects under their own user folder AND inside a
-- lecture folder that belongs to them.

insert into storage.buckets (id, name, public, allowed_mime_types)
values (
  'lectures',
  'lectures',
  false,
  array[
    'video/mp4', 'video/quicktime', 'video/webm', 'video/x-matroska',
    'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/mp4', 'audio/x-m4a', 'audio/webm', 'audio/ogg'
  ]
)
on conflict (id) do update
  set public = false,
      allowed_mime_types = excluded.allowed_mime_types;

create or replace function public.owns_lecture_object(object_name text)
returns boolean
language sql
stable
set search_path = ''
as $$
  select (storage.foldername(object_name))[1] = (select auth.uid())::text
    and exists (
      select 1
      from public.lectures l
      where l.id::text = (storage.foldername(object_name))[2]
        and l.user_id = (select auth.uid())
    );
$$;

revoke execute on function public.owns_lecture_object(text) from public, anon;
grant execute on function public.owns_lecture_object(text) to authenticated;

create policy "lecture_media_select_own"
  on storage.objects for select
  to authenticated
  using (bucket_id = 'lectures' and public.owns_lecture_object(name));

create policy "lecture_media_insert_own"
  on storage.objects for insert
  to authenticated
  with check (bucket_id = 'lectures' and public.owns_lecture_object(name));

create policy "lecture_media_update_own"
  on storage.objects for update
  to authenticated
  using (bucket_id = 'lectures' and public.owns_lecture_object(name))
  with check (bucket_id = 'lectures' and public.owns_lecture_object(name));

create policy "lecture_media_delete_own"
  on storage.objects for delete
  to authenticated
  using (bucket_id = 'lectures' and public.owns_lecture_object(name));
