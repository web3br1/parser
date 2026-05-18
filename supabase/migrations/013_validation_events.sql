create table public.validation_events (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,

  actor_user_id uuid references auth.users(id) on delete set null,
  action validation_action not null,

  target_type text not null,
  target_id uuid not null,

  previous_status text,
  new_status text,

  previous_value jsonb,
  new_value jsonb,

  reason text,
  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now()
);

create index idx_validation_workspace_id on public.validation_events(workspace_id);
create index idx_validation_actor on public.validation_events(actor_user_id);
create index idx_validation_target on public.validation_events(target_type, target_id);
create index idx_validation_action on public.validation_events(action);
