-- ─────────────────────────────────────────────────────────────────
-- Reclassify unknown item
-- Atômico: UPDATE unknown_queue + INSERT processing_jobs + validation_event
-- Retorna o job_id para o Python chamar dispatch depois
-- ─────────────────────────────────────────────────────────────────
create or replace function public.reclassify_unknown_item(
  p_item_id     uuid,
  p_fact_type   text,
  p_destination text,
  p_chunk_id    uuid,
  p_source_id   uuid,
  p_confidence  numeric  default 0.5,
  p_reason      text     default null,
  p_actor_user_id uuid   default auth.uid()
)
returns uuid    -- job_id
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row   public.unknown_facts_queue%rowtype;
  v_job_id uuid;
  v_resolution jsonb;
  v_actor_user_id uuid := coalesce(p_actor_user_id, auth.uid());
begin
  select * into v_row
  from public.unknown_facts_queue
  where id = p_item_id
  for update;

  if not found then
    raise exception 'unknown_item_not_found';
  end if;

  if not public.has_workspace_role_for_user(
    v_row.workspace_id,
    v_actor_user_id,
    array['owner','manager','reviewer']::workspace_role[]
  ) then
    raise exception 'permission_denied';
  end if;

  if v_row.status = 'mapped' then
    raise exception 'already_mapped';
  end if;
  if v_row.status = 'ignored' then
    raise exception 'already_ignored';
  end if;

  -- Criar processing_job atomicamente (outbox: job nasce queued dentro da transação)
  insert into public.processing_jobs (
    workspace_id, source_id, chunk_id,
    job_type, status, idempotency_key,
    metadata
  )
  values (
    v_row.workspace_id, p_source_id, p_chunk_id,
    'extraction', 'queued',
    encode(digest(
      'extraction:manual:' || p_item_id::text || ':' || p_fact_type || ':' || p_destination,
      'sha256'
    ), 'hex'),
    jsonb_build_object(
      'fact_type',                   p_fact_type,
      'destination',                 p_destination,
      'classification_confidence',   p_confidence,
      'classification_prompt_version', 'manual_reclassify',
      'classification_model',        'human'
    )
  )
  returning id into v_job_id;

  -- Resolução armazenada no item
  v_resolution := jsonb_build_object(
    'fact_type',          p_fact_type,
    'destination',        p_destination,
    'extraction_job_id',  v_job_id
  );

  update public.unknown_facts_queue
  set status      = 'mapped',
      resolution  = v_resolution::text,
      resolved_by = v_actor_user_id,
      resolved_at = now()
  where id = p_item_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason,
    metadata
  ) values (
    v_row.workspace_id, v_actor_user_id, 'manual_created',
    'unknown_item', p_item_id,
    v_row.status, 'mapped',
    jsonb_build_object('suggested_fact_type', v_row.suggested_fact_type),
    v_resolution,
    p_reason,
    jsonb_build_object('extraction_job_id', v_job_id, 'fact_type', p_fact_type)
  );

  return v_job_id;
end;
$$;


-- ─────────────────────────────────────────────────────────────────
-- Ignore unknown item
-- Atômico: UPDATE unknown_queue + validation_event
-- ─────────────────────────────────────────────────────────────────
create or replace function public.ignore_unknown_item(
  p_item_id uuid,
  p_reason  text default null,
  p_actor_user_id uuid default auth.uid()
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.unknown_facts_queue%rowtype;
  v_actor_user_id uuid := coalesce(p_actor_user_id, auth.uid());
begin
  select * into v_row
  from public.unknown_facts_queue
  where id = p_item_id
  for update;

  if not found then
    raise exception 'unknown_item_not_found';
  end if;

  if not public.has_workspace_role_for_user(
    v_row.workspace_id,
    v_actor_user_id,
    array['owner','manager','reviewer']::workspace_role[]
  ) then
    raise exception 'permission_denied';
  end if;

  -- idempotente
  if v_row.status = 'ignored' then
    return;
  end if;

  if v_row.status = 'mapped' then
    raise exception 'already_mapped';
  end if;

  update public.unknown_facts_queue
  set status      = 'ignored',
      resolved_by = v_actor_user_id,
      resolved_at = now()
  where id = p_item_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason
  ) values (
    v_row.workspace_id, v_actor_user_id, 'rejected',
    'unknown_item', p_item_id,
    v_row.status, 'ignored',
    jsonb_build_object('suggested_fact_type', v_row.suggested_fact_type),
    null,
    p_reason
  );
end;
$$;


-- ─────────────────────────────────────────────────────────────────
-- Reject fact (atômico: status transition + validation_event)
-- ─────────────────────────────────────────────────────────────────
create or replace function public.reject_fact(
  target_fact_id uuid,
  reason         text default null,
  actor_user_id uuid default auth.uid()
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.extracted_facts%rowtype;
  v_actor_user_id uuid := coalesce(actor_user_id, auth.uid());
begin
  select * into v_row
  from public.extracted_facts
  where id = target_fact_id
  for update;

  if not found then
    raise exception 'fact_not_found';
  end if;

  if not public.has_workspace_role_for_user(
    v_row.workspace_id,
    v_actor_user_id,
    array['owner','manager','reviewer']::workspace_role[]
  ) then
    raise exception 'permission_denied';
  end if;

  -- idempotente: já rejected → ok
  if v_row.status = 'rejected' then
    return target_fact_id;
  end if;

  if v_row.status in ('published', 'deprecated', 'superseded') then
    raise exception 'invalid_fact_status_for_rejection: %', v_row.status;
  end if;

  update public.extracted_facts
  set status = 'rejected',
      reviewed_by = v_actor_user_id,
      reviewed_at = now()
  where id = target_fact_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason
  ) values (
    v_row.workspace_id, v_actor_user_id, 'rejected',
    'extracted_fact', target_fact_id,
    v_row.status::text, 'rejected',
    v_row.content, null, reason
  );

  return target_fact_id;
end;
$$;


-- ─────────────────────────────────────────────────────────────────
-- Reject rule
-- ─────────────────────────────────────────────────────────────────
create or replace function public.reject_rule(
  target_rule_id uuid,
  reason         text default null,
  actor_user_id uuid default auth.uid()
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.business_rules%rowtype;
  v_actor_user_id uuid := coalesce(actor_user_id, auth.uid());
begin
  select * into v_row
  from public.business_rules
  where id = target_rule_id
  for update;

  if not found then
    raise exception 'rule_not_found';
  end if;

  if not public.has_workspace_role_for_user(
    v_row.workspace_id,
    v_actor_user_id,
    array['owner','manager','reviewer']::workspace_role[]
  ) then
    raise exception 'permission_denied';
  end if;

  if v_row.status = 'rejected' then
    return target_rule_id;
  end if;

  if v_row.status in ('published', 'deprecated', 'superseded') then
    raise exception 'invalid_rule_status_for_rejection: %', v_row.status;
  end if;

  update public.business_rules
  set status = 'rejected',
      reviewed_by = v_actor_user_id,
      reviewed_at = now()
  where id = target_rule_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason
  ) values (
    v_row.workspace_id, v_actor_user_id, 'rejected',
    'business_rule', target_rule_id,
    v_row.status::text, 'rejected',
    jsonb_build_object('condition', v_row.condition, 'action', v_row.action),
    null, reason
  );

  return target_rule_id;
end;
$$;


-- ─────────────────────────────────────────────────────────────────
-- Create fact version (edit — nova versão, não edição in-place)
-- Python insere conteúdo já validado via Pydantic.
-- ─────────────────────────────────────────────────────────────────
create or replace function public.create_fact_version(
  old_fact_id              uuid,
  new_content              jsonb,
  new_normalized_content   jsonb,
  reason                   text default null,
  actor_user_id            uuid default auth.uid()
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  old_row      public.extracted_facts%rowtype;
  new_fact_id  uuid;
  v_actor_user_id uuid := coalesce(actor_user_id, auth.uid());
begin
  select * into old_row
  from public.extracted_facts
  where id = old_fact_id
  for update;

  if not found then
    raise exception 'fact_not_found';
  end if;

  if not public.has_workspace_role_for_user(
    old_row.workspace_id,
    v_actor_user_id,
    array['owner','manager','reviewer']::workspace_role[]
  ) then
    raise exception 'permission_denied';
  end if;

  if old_row.superseded_by is not null then
    raise exception 'fact_already_superseded: %', old_row.superseded_by;
  end if;

  if old_row.status in ('published', 'deprecated') then
    raise exception 'invalid_fact_status_for_versioning: %', old_row.status;
  end if;

  -- Inserir nova versão
  insert into public.extracted_facts (
    workspace_id, source_id, chunk_id, evidence_span_id,
    fact_type, schema_version,
    content, normalized_content,
    status,
    confidence, model_name, model_provider, prompt_version, extraction_run_id,
    supersedes,
    created_by, reviewed_by, reviewed_at
  )
  values (
    old_row.workspace_id, old_row.source_id, old_row.chunk_id, old_row.evidence_span_id,
    old_row.fact_type, old_row.schema_version,
    new_content, new_normalized_content,
    'approved',
    old_row.confidence, old_row.model_name, old_row.model_provider,
    old_row.prompt_version, old_row.extraction_run_id,
    old_fact_id,
    v_actor_user_id, v_actor_user_id, now()
  )
  returning id into new_fact_id;

  -- Marcar original como superseded
  update public.extracted_facts
  set status = 'superseded',
      superseded_by = new_fact_id
  where id = old_fact_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason,
    metadata
  ) values (
    old_row.workspace_id, v_actor_user_id, 'edited',
    'extracted_fact', old_fact_id,
    old_row.status::text, 'superseded',
    old_row.content, new_content, reason,
    jsonb_build_object('new_fact_id', new_fact_id)
  );

  return new_fact_id;
end;
$$;


-- ─────────────────────────────────────────────────────────────────
-- Create rule version (edit — nova versão, não edição in-place)
-- ─────────────────────────────────────────────────────────────────
create or replace function public.create_rule_version(
  old_rule_id    uuid,
  new_condition  jsonb,
  new_action     jsonb,
  reason         text default null,
  actor_user_id  uuid default auth.uid()
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  old_row      public.business_rules%rowtype;
  new_rule_id  uuid;
  v_actor_user_id uuid := coalesce(actor_user_id, auth.uid());
begin
  select * into old_row
  from public.business_rules
  where id = old_rule_id
  for update;

  if not found then
    raise exception 'rule_not_found';
  end if;

  if not public.has_workspace_role_for_user(
    old_row.workspace_id,
    v_actor_user_id,
    array['owner','manager','reviewer']::workspace_role[]
  ) then
    raise exception 'permission_denied';
  end if;

  if old_row.superseded_by is not null then
    raise exception 'rule_already_superseded: %', old_row.superseded_by;
  end if;

  if old_row.status in ('published', 'deprecated') then
    raise exception 'invalid_rule_status_for_versioning: %', old_row.status;
  end if;

  -- Inserir nova versão
  insert into public.business_rules (
    workspace_id, source_id, chunk_id, evidence_span_id,
    rule_type, schema_version,
    condition, action,
    status, priority,
    confidence, model_name, model_provider, prompt_version, extraction_run_id,
    supersedes,
    created_by, reviewed_by, reviewed_at
  )
  values (
    old_row.workspace_id, old_row.source_id, old_row.chunk_id, old_row.evidence_span_id,
    old_row.rule_type, old_row.schema_version,
    new_condition, new_action,
    'approved', old_row.priority,
    old_row.confidence, old_row.model_name, old_row.model_provider,
    old_row.prompt_version, old_row.extraction_run_id,
    old_rule_id,
    v_actor_user_id, v_actor_user_id, now()
  )
  returning id into new_rule_id;

  update public.business_rules
  set status = 'superseded',
      superseded_by = new_rule_id
  where id = old_rule_id;

  insert into public.validation_events (
    workspace_id, actor_user_id, action,
    target_type, target_id,
    previous_status, new_status,
    previous_value, new_value, reason,
    metadata
  ) values (
    old_row.workspace_id, v_actor_user_id, 'edited',
    'business_rule', old_rule_id,
    old_row.status::text, 'superseded',
    jsonb_build_object('condition', old_row.condition, 'action', old_row.action),
    jsonb_build_object('condition', new_condition, 'action', new_action),
    reason,
    jsonb_build_object('new_rule_id', new_rule_id)
  );

  return new_rule_id;
end;
$$;
