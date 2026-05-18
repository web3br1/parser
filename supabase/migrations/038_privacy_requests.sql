create table public.privacy_requests (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  request_type text not null check (request_type in ('export', 'delete')),
  status text not null check (status in ('requested', 'dry_run', 'processing', 'completed', 'cancelled', 'failed')),
  requested_by uuid references auth.users(id) on delete set null,
  dry_run_plan jsonb not null default '{}'::jsonb,
  confirmation_required boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_privacy_requests_workspace_id
on public.privacy_requests(workspace_id);

create index idx_privacy_requests_workspace_status
on public.privacy_requests(workspace_id, status);

create trigger trg_privacy_requests_updated_at
before update on public.privacy_requests
for each row execute function public.touch_updated_at();

alter table public.privacy_requests enable row level security;

create policy "owners can view privacy requests"
on public.privacy_requests
for select
using (public.has_workspace_role(workspace_id, array['owner']::workspace_role[]));
