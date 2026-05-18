create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid references public.workspaces(id) on delete cascade,
  actor_user_id uuid references auth.users(id) on delete set null,

  action text not null,
  resource_type text not null,
  resource_id uuid,

  input_hash text,
  output_hash text,

  ip_address inet,
  user_agent text,

  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now()
);

create index idx_audit_workspace_id on public.audit_logs(workspace_id);
create index idx_audit_actor_user_id on public.audit_logs(actor_user_id);
create index idx_audit_resource on public.audit_logs(resource_type, resource_id);
create index idx_audit_action on public.audit_logs(action);
create index idx_audit_created_at on public.audit_logs(created_at);
