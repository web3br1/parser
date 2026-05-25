create table public.source_pack_import_runs (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  actor_user_id uuid references auth.users(id) on delete set null,

  source_pack_id text,
  source_pack_version text,
  source_dir text,
  input_hash text not null,

  status text not null check (status in ('preflighted', 'compiled', 'rejected', 'failed')),
  recommended_action text not null check (recommended_action in ('compile_as_source_pack', 'normal_ingest', 'reject')),

  bundle_hash text,
  context_version text,
  output_path text,
  readiness_status text check (readiness_status is null or readiness_status in ('ready', 'warning', 'blocked')),
  readiness_score integer check (readiness_score is null or (readiness_score >= 0 and readiness_score <= 100)),

  numbered_source_count integer not null default 0 check (numbered_source_count >= 0),
  csv_count integer not null default 0 check (csv_count >= 0),
  markdown_count integer not null default 0 check (markdown_count >= 0),
  manifest_document_count integer not null default 0 check (manifest_document_count >= 0),
  official_reference_count integer not null default 0 check (official_reference_count >= 0),

  missing_files jsonb not null default '[]'::jsonb,
  extra_files jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  errors jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_source_pack_import_runs_workspace_id
on public.source_pack_import_runs(workspace_id);

create index idx_source_pack_import_runs_actor_user_id
on public.source_pack_import_runs(actor_user_id);

create index idx_source_pack_import_runs_input_hash
on public.source_pack_import_runs(workspace_id, input_hash);

create index idx_source_pack_import_runs_pack
on public.source_pack_import_runs(workspace_id, source_pack_id, source_pack_version);

create index idx_source_pack_import_runs_status
on public.source_pack_import_runs(workspace_id, status);

create index idx_source_pack_import_runs_created_at
on public.source_pack_import_runs(created_at);

create trigger trg_source_pack_import_runs_updated_at
before update on public.source_pack_import_runs
for each row execute function public.touch_updated_at();

alter table public.source_pack_import_runs enable row level security;

revoke all on public.source_pack_import_runs from anon, authenticated;
grant all on public.source_pack_import_runs to service_role;
