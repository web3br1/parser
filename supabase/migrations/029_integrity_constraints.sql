create unique index if not exists uq_sources_workspace_file_hash_active
on public.sources(workspace_id, file_hash)
where deleted_at is null and file_hash is not null;

create or replace function public.get_or_create_processing_job(
  target_workspace_id uuid,
  target_source_id uuid,
  target_chunk_id uuid,
  target_job_type text,
  target_idempotency_key text,
  job_metadata jsonb default '{}'::jsonb
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  job_id uuid;
begin
  insert into public.processing_jobs (
    workspace_id,
    source_id,
    chunk_id,
    job_type,
    status,
    idempotency_key,
    metadata
  )
  values (
    target_workspace_id,
    target_source_id,
    target_chunk_id,
    target_job_type,
    'queued',
    target_idempotency_key,
    coalesce(job_metadata, '{}'::jsonb)
  )
  on conflict (idempotency_key)
  do update set updated_at = public.processing_jobs.updated_at
  returning id into job_id;

  return job_id;
end;
$$;
