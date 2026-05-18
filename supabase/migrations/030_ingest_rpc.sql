create or replace function public.complete_ingest_job(
  target_job_id uuid,
  target_source_id uuid,
  target_workspace_id uuid,
  quality_report jsonb,
  chunk_items jsonb
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  chunks_created integer := jsonb_array_length(coalesce(chunk_items, '[]'::jsonb));
begin
  insert into public.source_quality_reports (
    workspace_id,
    source_id,
    is_processable,
    detected_issues,
    decision
  )
  values (
    target_workspace_id,
    target_source_id,
    coalesce((quality_report->>'passed')::boolean, true),
    coalesce(quality_report->'warnings', '[]'::jsonb),
    case
      when coalesce((quality_report->>'passed')::boolean, true) then 'passed'
      else coalesce(quality_report->>'rejection_reason', 'failed')
    end
  )
  on conflict (source_id)
  do update set
    is_processable = excluded.is_processable,
    detected_issues = excluded.detected_issues,
    decision = excluded.decision;

  delete from public.chunks
  where source_id = target_source_id;

  insert into public.chunks (
    workspace_id,
    source_id,
    chunk_index,
    status,
    content,
    content_hash,
    page_start,
    page_end,
    sheet_name,
    row_start,
    row_end,
    section_title,
    token_count,
    metadata
  )
  select
    target_workspace_id,
    target_source_id,
    c.chunk_index,
    'pending',
    c.content,
    c.content_hash,
    c.page_start,
    c.page_end,
    c.sheet_name,
    c.row_start,
    c.row_end,
    c.section_title,
    c.token_count,
    coalesce(c.metadata, '{}'::jsonb)
  from jsonb_to_recordset(coalesce(chunk_items, '[]'::jsonb)) as c(
    chunk_index integer,
    content text,
    content_hash text,
    page_start integer,
    page_end integer,
    sheet_name text,
    row_start integer,
    row_end integer,
    section_title text,
    token_count integer,
    metadata jsonb
  );

  update public.sources
  set status = 'processing'
  where id = target_source_id
    and workspace_id = target_workspace_id;

  update public.processing_jobs
  set
    status = 'succeeded',
    finished_at = now(),
    metadata = jsonb_set(
      coalesce(metadata, '{}'::jsonb),
      '{chunks_created}',
      to_jsonb(chunks_created),
      true
    )
  where id = target_job_id
    and source_id = target_source_id
    and workspace_id = target_workspace_id;
end;
$$;
