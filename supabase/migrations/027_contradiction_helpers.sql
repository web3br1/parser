create or replace function public.mark_fact_contradiction(
  target_workspace_id uuid,
  target_fact_ids uuid[],
  description text,
  severity risk_level default 'medium'
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  contradiction_id uuid;
begin
  if not public.has_workspace_role(target_workspace_id, array['owner','manager','reviewer']::workspace_role[]) then
    raise exception 'permission_denied';
  end if;

  if coalesce(array_length(target_fact_ids, 1), 0) < 2 then
    raise exception 'contradiction_requires_at_least_two_facts';
  end if;

  insert into public.contradictions (
    workspace_id,
    fact_ids,
    description,
    severity,
    status
  )
  values (
    target_workspace_id,
    target_fact_ids,
    description,
    severity,
    'open'
  )
  returning id into contradiction_id;

  update public.extracted_facts
  set status = 'conflicted'
  where workspace_id = target_workspace_id
    and id = any(target_fact_ids)
    and status in ('approved', 'published');

  insert into public.validation_events (
    workspace_id,
    actor_user_id,
    action,
    target_type,
    target_id,
    previous_status,
    new_status,
    new_value,
    reason
  )
  values (
    target_workspace_id,
    auth.uid(),
    'conflict_marked',
    'contradiction',
    contradiction_id,
    null,
    'open',
    jsonb_build_object('fact_ids', target_fact_ids),
    description
  );

  return contradiction_id;
end;
$$;
