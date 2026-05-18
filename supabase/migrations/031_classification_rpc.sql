create or replace function public.complete_classification_job(
  target_job_id uuid,
  target_chunk_id uuid,
  target_workspace_id uuid,
  target_source_id uuid,
  classification_payload jsonb,
  new_chunk_status text,
  unknown_items jsonb,
  extraction_jobs jsonb,
  job_idempotency_key text
)
returns uuid[]
language plpgsql
security definer
set search_path = public
as $$
declare
  item record;
  queued_job record;
  extraction_job_ids uuid[] := '{}';
  inserted_job_id uuid;
begin
  update public.chunks
  set
    classification = coalesce(classification_payload, '{}'::jsonb),
    status = new_chunk_status::chunk_status
  where id = target_chunk_id
    and workspace_id = target_workspace_id
    and source_id = target_source_id;

  for item in
    select *
    from jsonb_to_recordset(coalesce(unknown_items, '[]'::jsonb)) as x(
      raw_text text,
      suggested_fact_type text,
      confidence numeric,
      metadata jsonb
    )
  loop
    insert into public.unknown_facts_queue (
      workspace_id,
      source_id,
      chunk_id,
      raw_text,
      suggested_fact_type,
      confidence,
      metadata
    )
    values (
      target_workspace_id,
      target_source_id,
      target_chunk_id,
      item.raw_text,
      item.suggested_fact_type,
      item.confidence,
      coalesce(item.metadata, '{}'::jsonb)
    );
  end loop;

  for queued_job in
    select *
    from jsonb_to_recordset(coalesce(extraction_jobs, '[]'::jsonb)) as x(
      workspace_id uuid,
      source_id uuid,
      chunk_id uuid,
      job_type text,
      status text,
      idempotency_key text,
      metadata jsonb
    )
  loop
    inserted_job_id := public.get_or_create_processing_job(
      queued_job.workspace_id,
      queued_job.source_id,
      queued_job.chunk_id,
      queued_job.job_type,
      queued_job.idempotency_key,
      coalesce(queued_job.metadata, '{}'::jsonb)
    );
    extraction_job_ids := array_append(extraction_job_ids, inserted_job_id);
  end loop;

  update public.processing_jobs
  set
    status = 'succeeded',
    idempotency_key = job_idempotency_key,
    finished_at = now()
  where id = target_job_id
    and workspace_id = target_workspace_id
    and source_id = target_source_id
    and chunk_id = target_chunk_id;

  return extraction_job_ids;
end;
$$;
