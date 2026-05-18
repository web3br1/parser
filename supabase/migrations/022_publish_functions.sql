create or replace function public.approve_fact(
  target_fact_id uuid,
  replacement_content jsonb default null,
  replacement_normalized_content jsonb default null,
  reason text default null,
  actor_user_id uuid default auth.uid()
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  before_row public.extracted_facts%rowtype;
  after_row public.extracted_facts%rowtype;
  v_actor_user_id uuid := coalesce(actor_user_id, auth.uid());
begin
  select *
  into before_row
  from public.extracted_facts
  where id = target_fact_id
  for update;

  if not found then
    raise exception 'fact_not_found';
  end if;

  if not public.has_workspace_role_for_user(
    before_row.workspace_id,
    v_actor_user_id,
    array['owner','manager','reviewer']::workspace_role[]
  ) then
    raise exception 'permission_denied';
  end if;

  if before_row.status not in ('extracted', 'needs_review', 'approved') then
    raise exception 'invalid_fact_status_for_approval: %', before_row.status;
  end if;

  update public.extracted_facts
  set
    content = coalesce(replacement_content, content),
    normalized_content = coalesce(replacement_normalized_content, normalized_content),
    status = 'approved',
    reviewed_by = v_actor_user_id,
    reviewed_at = now()
  where id = target_fact_id
  returning *
  into after_row;

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
    before_row.workspace_id,
    v_actor_user_id,
    case when replacement_content is null then 'approved' else 'edited' end,
    'extracted_fact',
    target_fact_id,
    before_row.status::text,
    after_row.status::text,
    jsonb_build_object('content', before_row.content, 'normalized_content', before_row.normalized_content),
    jsonb_build_object('content', after_row.content, 'normalized_content', after_row.normalized_content),
    reason
  );

  return target_fact_id;
end;
$$;

create or replace function public.publish_fact(
  target_fact_id uuid,
  reason text default null,
  actor_user_id uuid default auth.uid()
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  before_row public.extracted_facts%rowtype;
  after_row public.extracted_facts%rowtype;
  v_actor_user_id uuid := coalesce(actor_user_id, auth.uid());
begin
  select *
  into before_row
  from public.extracted_facts
  where id = target_fact_id
  for update;

  if not found then
    raise exception 'fact_not_found';
  end if;

  if not public.has_workspace_role_for_user(
    before_row.workspace_id,
    v_actor_user_id,
    array['owner','manager','reviewer']::workspace_role[]
  ) then
    raise exception 'permission_denied';
  end if;

  if before_row.status <> 'approved' then
    raise exception 'invalid_fact_status_for_publish: %', before_row.status;
  end if;

  if exists (
    select 1
    from public.contradictions c
    where c.workspace_id = before_row.workspace_id
      and c.status in ('open', 'needs_review')
      and before_row.id = any(c.fact_ids)
  ) then
    raise exception 'fact_has_open_contradiction';
  end if;

  update public.extracted_facts
  set
    status = 'published',
    published_by = v_actor_user_id,
    published_at = now()
  where id = target_fact_id
  returning *
  into after_row;

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
    before_row.workspace_id,
    v_actor_user_id,
    'published',
    'extracted_fact',
    target_fact_id,
    before_row.status::text,
    after_row.status::text,
    before_row.content,
    after_row.content,
    reason
  );

  return target_fact_id;
end;
$$;

create or replace function public.approve_rule(
  target_rule_id uuid,
  replacement_condition jsonb default null,
  replacement_action jsonb default null,
  reason text default null,
  actor_user_id uuid default auth.uid()
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  before_row public.business_rules%rowtype;
  after_row public.business_rules%rowtype;
  v_actor_user_id uuid := coalesce(actor_user_id, auth.uid());
begin
  select *
  into before_row
  from public.business_rules
  where id = target_rule_id
  for update;

  if not found then
    raise exception 'rule_not_found';
  end if;

  if not public.has_workspace_role_for_user(
    before_row.workspace_id,
    v_actor_user_id,
    array['owner','manager','reviewer']::workspace_role[]
  ) then
    raise exception 'permission_denied';
  end if;

  if before_row.status not in ('extracted', 'needs_review', 'approved') then
    raise exception 'invalid_rule_status_for_approval: %', before_row.status;
  end if;

  update public.business_rules
  set
    condition = coalesce(replacement_condition, condition),
    action = coalesce(replacement_action, action),
    status = 'approved',
    reviewed_by = v_actor_user_id,
    reviewed_at = now()
  where id = target_rule_id
  returning *
  into after_row;

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
    before_row.workspace_id,
    v_actor_user_id,
    case when replacement_condition is null and replacement_action is null then 'approved' else 'edited' end,
    'business_rule',
    target_rule_id,
    before_row.status::text,
    after_row.status::text,
    jsonb_build_object('condition', before_row.condition, 'action', before_row.action),
    jsonb_build_object('condition', after_row.condition, 'action', after_row.action),
    reason
  );

  return target_rule_id;
end;
$$;

create or replace function public.publish_rule(
  target_rule_id uuid,
  reason text default null,
  actor_user_id uuid default auth.uid()
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  before_row public.business_rules%rowtype;
  after_row public.business_rules%rowtype;
  v_actor_user_id uuid := coalesce(actor_user_id, auth.uid());
begin
  select *
  into before_row
  from public.business_rules
  where id = target_rule_id
  for update;

  if not found then
    raise exception 'rule_not_found';
  end if;

  if not public.has_workspace_role_for_user(
    before_row.workspace_id,
    v_actor_user_id,
    array['owner','manager','reviewer']::workspace_role[]
  ) then
    raise exception 'permission_denied';
  end if;

  if before_row.status <> 'approved' then
    raise exception 'invalid_rule_status_for_publish: %', before_row.status;
  end if;

  if exists (
    select 1
    from public.contradictions c
    where c.workspace_id = before_row.workspace_id
      and c.status in ('open', 'needs_review')
      and before_row.id = any(c.rule_ids)
  ) then
    raise exception 'rule_has_open_contradiction';
  end if;

  update public.business_rules
  set
    status = 'published',
    published_by = v_actor_user_id,
    published_at = now()
  where id = target_rule_id
  returning *
  into after_row;

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
    before_row.workspace_id,
    v_actor_user_id,
    'published',
    'business_rule',
    target_rule_id,
    before_row.status::text,
    after_row.status::text,
    jsonb_build_object('condition', before_row.condition, 'action', before_row.action),
    jsonb_build_object('condition', after_row.condition, 'action', after_row.action),
    reason
  );

  return target_rule_id;
end;
$$;
