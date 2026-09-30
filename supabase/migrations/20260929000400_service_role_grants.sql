-- Projects created without automatic table grants give service_role nothing on
-- new tables. Server-side workers (later phases) use service_role, so grant it
-- explicitly. service_role bypasses RLS by design and is never exposed to clients.

grant all on table public.profiles to service_role;
grant all on table public.lectures to service_role;
