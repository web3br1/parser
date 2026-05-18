alter type public.source_status add value if not exists 'extracted' after 'processing';

alter table public.processing_jobs
  add column if not exists worker_id text;

create index if not exists idx_jobs_worker_id on public.processing_jobs(worker_id);

create or replace function public.claim_processing_job(
  p_job_id uuid,
  p_worker_id text
)
returns public.processing_jobs
language sql
security definer
set search_path = public
as $$
  update public.processing_jobs
  set status = 'running',
      started_at = now(),
      worker_id = p_worker_id,
      error_code = null,
      error_message = null,
      updated_at = now()
  where id = p_job_id
    and status in ('queued', 'retrying')
  returning *;
$$;

create or replace function public.finalize_source_state_after_extraction(
  p_source_id uuid,
  p_workspace_id uuid
)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  remaining_active integer;
  unpublished_records integer;
  review_pending_records integer;
  source_records integer;
  next_status text;
begin
  select count(*)
  into remaining_active
  from public.processing_jobs
  where source_id = p_source_id
    and workspace_id = p_workspace_id
    and status in ('queued', 'running', 'retrying');

  if remaining_active > 0 then
    return null;
  end if;

  if exists (
    select 1
    from public.processing_jobs
    where source_id = p_source_id
      and workspace_id = p_workspace_id
      and status = 'failed'
  ) then
    next_status := 'failed';
  else
    select count(*)
    into source_records
    from (
      select id
      from public.extracted_facts
      where source_id = p_source_id
        and workspace_id = p_workspace_id
      union all
      select id
      from public.business_rules
      where source_id = p_source_id
        and workspace_id = p_workspace_id
    ) records;

    select count(*)
    into unpublished_records
    from (
      select id
      from public.extracted_facts
      where source_id = p_source_id
        and workspace_id = p_workspace_id
        and status not in ('published', 'rejected')
      union all
      select id
      from public.business_rules
      where source_id = p_source_id
        and workspace_id = p_workspace_id
        and status not in ('published', 'rejected')
    ) records;

    select count(*)
    into review_pending_records
    from (
      select id
      from public.chunks
      where source_id = p_source_id
        and workspace_id = p_workspace_id
        and status = 'needs_review'
      union all
      select id
      from public.unknown_facts_queue
      where source_id = p_source_id
        and workspace_id = p_workspace_id
        and status in ('open', 'schema_requested')
        and resolved_at is null
      union all
      select id
      from public.extracted_facts
      where source_id = p_source_id
        and workspace_id = p_workspace_id
        and status in ('needs_review', 'conflicted')
      union all
      select id
      from public.business_rules
      where source_id = p_source_id
        and workspace_id = p_workspace_id
        and status in ('needs_review', 'conflicted')
      union all
      select c.id
      from public.contradictions c
      where c.workspace_id = p_workspace_id
        and c.status in ('open', 'needs_review')
        and (
          exists (
            select 1
            from public.extracted_facts f
            where f.source_id = p_source_id
              and f.workspace_id = p_workspace_id
              and f.id = any(c.fact_ids)
          )
          or exists (
            select 1
            from public.business_rules r
            where r.source_id = p_source_id
              and r.workspace_id = p_workspace_id
              and r.id = any(c.rule_ids)
          )
        )
    ) records;

    if review_pending_records > 0 then
      next_status := 'needs_review';
    elsif source_records > 0 and unpublished_records = 0 then
      next_status := 'published';
    else
      next_status := 'extracted';
    end if;
  end if;

  update public.sources
  set status = next_status::source_status,
      updated_at = now()
  where id = p_source_id
    and workspace_id = p_workspace_id
    and status in ('processing', 'extracted', 'needs_review');

  return next_status;
end;
$$;

revoke execute on function public.claim_processing_job(uuid, text) from public;
revoke execute on function public.claim_processing_job(uuid, text) from anon;
revoke execute on function public.claim_processing_job(uuid, text) from authenticated;
grant execute on function public.claim_processing_job(uuid, text) to service_role;

revoke execute on function public.finalize_source_state_after_extraction(uuid, uuid) from public;
revoke execute on function public.finalize_source_state_after_extraction(uuid, uuid) from anon;
revoke execute on function public.finalize_source_state_after_extraction(uuid, uuid) from authenticated;
grant execute on function public.finalize_source_state_after_extraction(uuid, uuid) to service_role;
