-- Phase 7B: stop endlessly re-running jobs whose worker keeps dying.
--
-- Previously, a job whose lease expired (worker crashed, killed, or out of memory)
-- was always put back in the queue. A job that reliably crashes its worker would
-- therefore loop forever, since the attempt limit is only checked when a stage
-- fails normally. Now an abandoned job that has already used all of its attempts
-- is marked failed (retryable, so the owner can retry it) and its lecture FAILED;
-- other abandoned jobs are re-queued as before.

create or replace function public.recover_processing_jobs(p_limit integer default 50)
returns table (job_id uuid)
language plpgsql
security definer
set search_path = ''
as $$
begin
  with exhausted as (
    update public.processing_jobs
       set status = 'failed',
           lease_owner = null,
           lease_expires_at = null,
           error_code = 'processing_interrupted',
           error_message = 'Processing was interrupted repeatedly and has been stopped. You can retry it.',
           retryable = true,
           status_detail = null,
           failed_at = now(),
           finished_at = now()
     where status = 'running' and lease_expires_at < now() and attempt_count >= max_attempts
    returning lecture_id
  )
  update public.lectures l
     set status = 'FAILED'
    from exhausted e
   where l.id = e.lecture_id and l.status not in ('READY', 'FAILED');

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

revoke execute on function public.recover_processing_jobs(integer) from public, anon, authenticated;
grant execute on function public.recover_processing_jobs(integer) to service_role;
