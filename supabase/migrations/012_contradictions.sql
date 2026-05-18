create table public.contradictions (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,

  fact_type text,
  rule_type text,

  fact_ids uuid[] not null default '{}',
  rule_ids uuid[] not null default '{}',

  description text not null,
  severity risk_level not null default 'medium',

  status text not null default 'open',
  resolved_by uuid references auth.users(id) on delete set null,
  resolution_note text,
  resolved_at timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  check (status in ('open', 'resolved', 'ignored', 'needs_review'))
);

create index idx_contradictions_workspace_id on public.contradictions(workspace_id);
create index idx_contradictions_status on public.contradictions(status);
create index idx_contradictions_severity on public.contradictions(severity);

create trigger trg_contradictions_updated_at
before update on public.contradictions
for each row execute function public.touch_updated_at();
