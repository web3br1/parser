create table public.processing_jobs (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  source_id uuid references public.sources(id) on delete cascade,
  chunk_id uuid references public.chunks(id) on delete cascade,

  job_type text not null,
  status job_status not null default 'queued',

  idempotency_key text not null,

  attempts integer not null default 0,
  max_attempts integer not null default 3,

  error_code text,
  error_message text,

  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  metadata jsonb not null default '{}'::jsonb,

  unique(idempotency_key)
);

create index idx_jobs_workspace_id on public.processing_jobs(workspace_id);
create index idx_jobs_source_id on public.processing_jobs(source_id);
create index idx_jobs_chunk_id on public.processing_jobs(chunk_id);
create index idx_jobs_status on public.processing_jobs(status);
create index idx_jobs_type on public.processing_jobs(job_type);

create trigger trg_processing_jobs_updated_at
before update on public.processing_jobs
for each row execute function public.touch_updated_at();
