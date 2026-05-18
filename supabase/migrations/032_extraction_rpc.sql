create or replace function public.complete_extraction_job(
  target_job_id uuid,
  target_chunk_id uuid,
  target_workspace_id uuid,
  target_source_id uuid,
  new_chunk_status text,
  job_idempotency_key text,
  unknown_item jsonb,
  evidence_span jsonb,
  fact_records jsonb,
  rule_record jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  evidence_id uuid;
  fact_item record;
  records_created integer := 0;
begin
  if evidence_span is not null then
    insert into public.evidence_spans (
      workspace_id,
      source_id,
      chunk_id,
      quote,
      quote_hash,
      char_start,
      char_end,
      page_number,
      sheet_name,
      row_number
    )
    values (
      target_workspace_id,
      target_source_id,
      target_chunk_id,
      evidence_span->>'quote',
      evidence_span->>'quote_hash',
      nullif(evidence_span->>'char_start', '')::integer,
      nullif(evidence_span->>'char_end', '')::integer,
      nullif(evidence_span->>'page_number', '')::integer,
      evidence_span->>'sheet_name',
      nullif(evidence_span->>'row_number', '')::integer
    )
    returning id into evidence_id;
  end if;

  if unknown_item is not null then
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
      unknown_item->>'raw_text',
      unknown_item->>'suggested_fact_type',
      nullif(unknown_item->>'confidence', '')::numeric,
      coalesce(unknown_item->'metadata', '{}'::jsonb)
    );
  end if;

  for fact_item in
    select *
    from jsonb_to_recordset(coalesce(fact_records, '[]'::jsonb)) as x(
      fact_type text,
      schema_version text,
      content jsonb,
      normalized_content jsonb,
      confidence numeric,
      model_name text,
      prompt_version text
    )
  loop
    insert into public.extracted_facts (
      workspace_id,
      source_id,
      chunk_id,
      evidence_span_id,
      fact_type,
      schema_version,
      content,
      normalized_content,
      confidence,
      status,
      model_name,
      prompt_version
    )
    values (
      target_workspace_id,
      target_source_id,
      target_chunk_id,
      evidence_id,
      fact_item.fact_type,
      fact_item.schema_version,
      coalesce(fact_item.content, '{}'::jsonb),
      coalesce(fact_item.normalized_content, '{}'::jsonb),
      fact_item.confidence,
      'extracted',
      fact_item.model_name,
      fact_item.prompt_version
    );
    records_created := records_created + 1;
  end loop;

  if rule_record is not null then
    insert into public.business_rules (
      workspace_id,
      source_id,
      chunk_id,
      evidence_span_id,
      rule_type,
      schema_version,
      condition,
      action,
      confidence,
      status,
      model_name,
      prompt_version
    )
    values (
      target_workspace_id,
      target_source_id,
      target_chunk_id,
      evidence_id,
      rule_record->>'rule_type',
      rule_record->>'schema_version',
      coalesce(rule_record->'condition', '{}'::jsonb),
      coalesce(rule_record->'action', '{}'::jsonb),
      nullif(rule_record->>'confidence', '')::numeric,
      'extracted',
      rule_record->>'model_name',
      rule_record->>'prompt_version'
    );
    records_created := records_created + 1;
  end if;

  update public.chunks
  set status = new_chunk_status::chunk_status
  where id = target_chunk_id
    and workspace_id = target_workspace_id
    and source_id = target_source_id;

  update public.processing_jobs
  set
    status = 'succeeded',
    idempotency_key = job_idempotency_key,
    finished_at = now(),
    metadata = jsonb_set(
      coalesce(metadata, '{}'::jsonb),
      '{records_created}',
      to_jsonb(records_created),
      true
    )
  where id = target_job_id
    and workspace_id = target_workspace_id
    and source_id = target_source_id
    and chunk_id = target_chunk_id;

  return jsonb_build_object(
    'records_created', records_created,
    'chunk_status', new_chunk_status
  );
end;
$$;
