create table public.source_quality_reports (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  source_id uuid not null references public.sources(id) on delete cascade,

  readability_score numeric(5,2),
  structure_score numeric(5,2),
  extractability_score numeric(5,2),
  noise_score numeric(5,2),
  final_score numeric(5,2),

  is_processable boolean not null default false,
  detected_issues jsonb not null default '[]'::jsonb,
  decision text not null default 'pending',

  created_at timestamptz not null default now(),

  unique(source_id)
);

create index idx_quality_workspace_id on public.source_quality_reports(workspace_id);
create index idx_quality_source_id on public.source_quality_reports(source_id);
