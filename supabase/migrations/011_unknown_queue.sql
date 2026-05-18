create table public.unknown_facts_queue (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  source_id uuid not null references public.sources(id) on delete cascade,
  chunk_id uuid not null references public.chunks(id) on delete cascade,
  evidence_span_id uuid references public.evidence_spans(id) on delete set null,

  raw_text text not null,
  suggested_fact_type text,
  suggested_schema jsonb,
  confidence numeric(5,4),

  status text not null default 'open',
  resolution text,
  resolved_by uuid references auth.users(id) on delete set null,
  resolved_at timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  check (status in ('open', 'mapped', 'ignored', 'schema_requested', 'resolved'))
);

create index idx_unknown_workspace_id on public.unknown_facts_queue(workspace_id);
create index idx_unknown_status on public.unknown_facts_queue(status);
create index idx_unknown_source_id on public.unknown_facts_queue(source_id);

create trigger trg_unknown_updated_at
before update on public.unknown_facts_queue
for each row execute function public.touch_updated_at();
