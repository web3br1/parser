create or replace function public.supersede_fact(
  old_fact_id uuid,
  replacement_fact_id uuid,
  reason text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  old_row public.extracted_facts%rowtype;
  replacement_row public.extracted_facts%rowtype;
begin
  select *
  into old_row
  from public.extracted_facts
  where id = old_fact_id
  for update;

  if not found then
    raise exception 'old_fact_not_found';
  end if;

  select *
  into replacement_row
  from public.extracted_facts
  where id = replacement_fact_id
  for update;

  if not found then
    raise exception 'replacement_fact_not_found';
  end if;

  if old_row.workspace_id <> replacement_row.workspace_id then
    raise exception 'workspace_mismatch';
  end if;

  if not public.has_workspace_role(old_row.workspace_id, array['owner','manager','reviewer']::workspace_role[]) then
    raise exception 'permission_denied';
  end if;

  update public.extracted_facts
  set
    status = 'superseded',
    superseded_by = replacement_fact_id
  where id = old_fact_id;

  update public.extracted_facts
  set
    supersedes = old_fact_id
  where id = replacement_fact_id;

  insert into public.validation_events (
    workspace_id,
    actor_user_id,
    action,
    target_type,
    target_id,
    previous_status,
    new_status,
    previous_value,
    new_value,
    reason
  )
  values (
    old_row.workspace_id,
    auth.uid(),
    'superseded',
    'extracted_fact',
    old_fact_id,
    old_row.status::text,
    'superseded',
    old_row.content,
    jsonb_build_object('superseded_by', replacement_fact_id),
    reason
  );

  return replacement_fact_id;
end;
$$;

create or replace function public.supersede_rule(
  old_rule_id uuid,
  replacement_rule_id uuid,
  reason text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  old_row public.business_rules%rowtype;
  replacement_row public.business_rules%rowtype;
begin
  select *
  into old_row
  from public.business_rules
  where id = old_rule_id
  for update;

  if not found then
    raise exception 'old_rule_not_found';
  end if;

  select *
  into replacement_row
  from public.business_rules
  where id = replacement_rule_id
  for update;

  if not found then
    raise exception 'replacement_rule_not_found';
  end if;

  if old_row.workspace_id <> replacement_row.workspace_id then
    raise exception 'workspace_mismatch';
  end if;

  if not public.has_workspace_role(old_row.workspace_id, array['owner','manager','reviewer']::workspace_role[]) then
    raise exception 'permission_denied';
  end if;

  update public.business_rules
  set
    status = 'superseded',
    superseded_by = replacement_rule_id
  where id = old_rule_id;

  update public.business_rules
  set
    supersedes = old_rule_id
  where id = replacement_rule_id;

  insert into public.validation_events (
    workspace_id,
    actor_user_id,
    action,
    target_type,
    target_id,
    previous_status,
    new_status,
    previous_value,
    new_value,
    reason
  )
  values (
    old_row.workspace_id,
    auth.uid(),
    'superseded',
    'business_rule',
    old_rule_id,
    old_row.status::text,
    'superseded',
    jsonb_build_object('condition', old_row.condition, 'action', old_row.action),
    jsonb_build_object('superseded_by', replacement_rule_id),
    reason
  );

  return replacement_rule_id;
end;
$$;

create or replace function public.rollback_source_publication(
  target_source_id uuid,
  reason text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  source_row public.sources%rowtype;
  affected_facts integer;
  affected_rules integer;
begin
  select *
  into source_row
  from public.sources
  where id = target_source_id
  for update;

  if not found then
    raise exception 'source_not_found';
  end if;

  if not public.has_workspace_role(source_row.workspace_id, array['owner','manager']::workspace_role[]) then
    raise exception 'permission_denied';
  end if;

  update public.extracted_facts
  set status = 'deprecated'
  where source_id = target_source_id
    and status in ('approved', 'published', 'conflicted');

  get diagnostics affected_facts = row_count;

  update public.business_rules
  set status = 'deprecated'
  where source_id = target_source_id
    and status in ('approved', 'published', 'conflicted');

  get diagnostics affected_rules = row_count;

  update public.sources
  set status = 'deprecated'
  where id = target_source_id;

  insert into public.validation_events (
    workspace_id,
    actor_user_id,
    action,
    target_type,
    target_id,
    previous_status,
    new_status,
    previous_value,
    new_value,
    reason,
    metadata
  )
  values (
    source_row.workspace_id,
    auth.uid(),
    'deprecated',
    'source',
    target_source_id,
    source_row.status::text,
    'deprecated',
    to_jsonb(source_row),
    jsonb_build_object('status', 'deprecated'),
    reason,
    jsonb_build_object(
      'deprecated_facts', affected_facts,
      'deprecated_rules', affected_rules
    )
  );

  return target_source_id;
end;
$$;
