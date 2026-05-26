create table public.context_build_runs (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  actor_user_id uuid references auth.users(id) on delete set null,

  input_mode text not null check (input_mode in (
    'single_document',
    'multi_document_batch',
    'source_pack'
  )),
  status text not null check (status in (
    'created',
    'preflighted',
    'queued',
    'processing',
    'needs_review',
    'ready_to_export',
    'compiled',
    'rejected',
    'failed'
  )),
  recommended_action text not null check (recommended_action in (
    'normal_ingest',
    'batch_ingest',
    'compile_as_source_pack',
    'reject'
  )),

  input_fingerprint text not null,
  input_hash text,
  source_dir text,
  source_pack_id text,
  source_pack_version text,
  staged_upload_id text,

  source_count integer not null default 0 check (source_count >= 0),
  job_count integer not null default 0 check (job_count >= 0),

  bundle_hash text,
  context_version text,
  output_path text,
  readiness_status text check (
    readiness_status is null or readiness_status in ('ready', 'warning', 'blocked')
  ),
  readiness_score integer check (
    readiness_score is null or (readiness_score >= 0 and readiness_score <= 100)
  ),

  file_counts jsonb not null default '{}'::jsonb,
  missing_files jsonb not null default '[]'::jsonb,
  extra_files jsonb not null default '[]'::jsonb,
  steps jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  errors jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_context_build_runs_workspace_created_at
on public.context_build_runs(workspace_id, created_at desc);

create index idx_context_build_runs_workspace_status
on public.context_build_runs(workspace_id, status);

create index idx_context_build_runs_workspace_input_mode
on public.context_build_runs(workspace_id, input_mode);

create index idx_context_build_runs_workspace_input_fingerprint
on public.context_build_runs(workspace_id, input_fingerprint);

create index idx_context_build_runs_workspace_input_hash
on public.context_build_runs(workspace_id, input_hash);

create index idx_context_build_runs_source_pack
on public.context_build_runs(workspace_id, source_pack_id, source_pack_version);

create trigger trg_context_build_runs_updated_at
before update on public.context_build_runs
for each row execute function public.touch_updated_at();

alter table public.context_build_runs enable row level security;

revoke all on public.context_build_runs from anon, authenticated;
grant all on public.context_build_runs to service_role;
