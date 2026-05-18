create or replace function public.create_workspace_with_owner(
  workspace_name text,
  workspace_slug text default null,
  workspace_settings jsonb default '{}'::jsonb,
  actor_user_id uuid default auth.uid()
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  new_workspace_id uuid;
  resolved_actor_user_id uuid := coalesce(actor_user_id, auth.uid());
begin
  if resolved_actor_user_id is null then
    raise exception 'not_authenticated';
  end if;

  insert into public.workspaces (
    name,
    slug,
    settings,
    created_by
  )
  values (
    workspace_name,
    workspace_slug,
    coalesce(workspace_settings, '{}'::jsonb),
    resolved_actor_user_id
  )
  returning id into new_workspace_id;

  insert into public.workspace_members (
    workspace_id,
    user_id,
    role,
    joined_at
  )
  values (
    new_workspace_id,
    resolved_actor_user_id,
    'owner',
    now()
  );

  return new_workspace_id;
end;
$$;

create policy "members can view active fact type schemas"
on public.fact_type_schemas
for select
using (
  status = 'active'
  or created_by = auth.uid()
);

create policy "owners can manage fact type schemas"
on public.fact_type_schemas
for all
using (
  created_by = auth.uid()
)
with check (
  created_by = auth.uid()
);
