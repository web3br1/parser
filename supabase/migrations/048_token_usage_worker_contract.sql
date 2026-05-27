alter table public.token_usage_log
  add column if not exists job_id uuid references public.processing_jobs(id) on delete set null,
  add column if not exists prompt_version text;

create index if not exists idx_token_usage_job_id
  on public.token_usage_log(job_id);
