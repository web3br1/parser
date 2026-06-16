-- TASK-040 grounding worker: additive grounding persistence.
--
-- Grounding is a Truth Contract review/publication safety signal. It is stored
-- in a side table so it never alters extracted_facts/business_rules published
-- columns or the context_bundle.v1 contract. Each row records the result of the
-- deterministic evidence check (Check A) and the independent entailment check
-- (Check B) for one extracted fact or rule candidate.

create table public.grounding_results (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  source_id uuid not null references public.sources(id) on delete cascade,
  chunk_id uuid not null references public.chunks(id) on delete cascade,

  -- A grounding result describes a single extracted candidate. Exactly one of
  -- fact_id / rule_id is expected to be set in normal flow, but both are
  -- optional so a result can be persisted before the candidate is routed to a
  -- reliable record (e.g. a required-grounding failure routed to review).
  fact_id uuid references public.extracted_facts(id) on delete cascade,
  rule_id uuid references public.business_rules(id) on delete cascade,

  -- Overall verdict for this candidate.
  grounding_status text not null check (
    grounding_status in ('not_required', 'passed', 'failed', 'abstained')
  ),
  grounding_required boolean not null default false,
  grounding_reason text,

  -- Check A - deterministic evidence.
  deterministic_status text check (
    deterministic_status is null or deterministic_status in ('passed', 'failed')
  ),
  deterministic_reason text,
  match_mode text check (
    match_mode is null or match_mode in ('exact', 'normalized', 'fuzzy')
  ),
  offset_status text,

  -- Check B - independent entailment.
  entailment_status text check (
    entailment_status is null or entailment_status in ('passed', 'failed', 'abstained')
  ),
  entailment_reason text,
  grounding_model text,
  grounding_prompt_version text,

  -- Re-grounding / cache keys. grounding_key is a stable hash over
  -- fact_or_rule_type + normalized_claim_payload + verified_quote +
  -- grounding_prompt_version + grounding_model. config_version pins the stakes
  -- config that decided whether grounding was required.
  grounding_key text,
  config_version text,

  grounding_checked_at timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_grounding_results_workspace_id
  on public.grounding_results(workspace_id);
create index idx_grounding_results_source_id
  on public.grounding_results(source_id);
create index idx_grounding_results_chunk_id
  on public.grounding_results(chunk_id);
create index idx_grounding_results_fact_id
  on public.grounding_results(fact_id);
create index idx_grounding_results_rule_id
  on public.grounding_results(rule_id);
create index idx_grounding_results_grounding_key
  on public.grounding_results(grounding_key);

create trigger trg_grounding_results_updated_at
before update on public.grounding_results
for each row execute function public.touch_updated_at();

-- RLS: raw, unreviewed truth-evaluation data. Browser clients must never read
-- or mutate it directly; the backend/API uses service_role. Matches the
-- review/raw knowledge tables in migration 020.
alter table public.grounding_results enable row level security;

revoke all on table public.grounding_results from anon;
revoke all on table public.grounding_results from authenticated;
grant all on table public.grounding_results to service_role;

create policy "managers can view grounding results"
on public.grounding_results
for select
using (public.has_workspace_role(workspace_id, array['owner','manager','reviewer']::workspace_role[]));

-- ---------------------------------------------------------------------------
-- complete_extraction_job successor.
--
-- Extends the RPC to atomically persist a grounding result in the same
-- transaction as the fact/rule/evidence rows. All existing arguments and
-- behavior are preserved; grounding_result is optional and defaults to no-op
-- when null. The argument list changes, so the prior 10-arg signature is
-- dropped before recreation.
-- ---------------------------------------------------------------------------

drop function if exists public.complete_extraction_job(
  uuid, uuid, uuid, uuid, text, text, jsonb, jsonb, jsonb, jsonb
);

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
  rule_record jsonb,
  grounding_result jsonb default null
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

  -- Atomic, additive grounding persistence. Workspace-scoped to the same tenant
  -- as the rest of the transaction; never alters published fact/rule columns.
  if grounding_result is not null then
    insert into public.grounding_results (
      workspace_id,
      source_id,
      chunk_id,
      fact_id,
      rule_id,
      grounding_status,
      grounding_required,
      grounding_reason,
      deterministic_status,
      deterministic_reason,
      match_mode,
      offset_status,
      entailment_status,
      entailment_reason,
      grounding_model,
      grounding_prompt_version,
      grounding_key,
      config_version,
      grounding_checked_at
    )
    values (
      target_workspace_id,
      target_source_id,
      target_chunk_id,
      nullif(grounding_result->>'fact_id', '')::uuid,
      nullif(grounding_result->>'rule_id', '')::uuid,
      grounding_result->>'grounding_status',
      coalesce((grounding_result->>'grounding_required')::boolean, false),
      grounding_result->>'grounding_reason',
      grounding_result->>'deterministic_status',
      grounding_result->>'deterministic_reason',
      grounding_result->>'match_mode',
      grounding_result->>'offset_status',
      grounding_result->>'entailment_status',
      grounding_result->>'entailment_reason',
      grounding_result->>'grounding_model',
      grounding_result->>'grounding_prompt_version',
      grounding_result->>'grounding_key',
      grounding_result->>'config_version',
      coalesce(
        nullif(grounding_result->>'grounding_checked_at', '')::timestamptz,
        now()
      )
    );
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

-- SECURITY DEFINER worker RPC: callable only by service_role (matches 036).
revoke execute on function public.complete_extraction_job(
  uuid, uuid, uuid, uuid, text, text, jsonb, jsonb, jsonb, jsonb, jsonb
) from public;
revoke execute on function public.complete_extraction_job(
  uuid, uuid, uuid, uuid, text, text, jsonb, jsonb, jsonb, jsonb, jsonb
) from anon;
revoke execute on function public.complete_extraction_job(
  uuid, uuid, uuid, uuid, text, text, jsonb, jsonb, jsonb, jsonb, jsonb
) from authenticated;
grant execute on function public.complete_extraction_job(
  uuid, uuid, uuid, uuid, text, text, jsonb, jsonb, jsonb, jsonb, jsonb
) to service_role;

-- ===========================================================================
-- ROLLBACK
-- ===========================================================================
-- Restores the prior 10-argument complete_extraction_job and drops the
-- grounding_results table. Run the statements below to revert this migration.
--
-- -- 1. Drop the 11-arg successor RPC.
-- drop function if exists public.complete_extraction_job(
--   uuid, uuid, uuid, uuid, text, text, jsonb, jsonb, jsonb, jsonb, jsonb
-- );
--
-- -- 2. Recreate the original 10-arg RPC from migration 032
-- --    (see supabase/migrations/032_extraction_rpc.sql for the full body) and
-- --    re-grant execute to service_role.
--
-- -- 3. Drop policies, trigger, and table.
-- drop policy if exists "managers can view grounding results" on public.grounding_results;
-- drop trigger if exists trg_grounding_results_updated_at on public.grounding_results;
-- drop table if exists public.grounding_results;
