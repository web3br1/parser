create table public.token_usage_log (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  source_id uuid references public.sources(id) on delete set null,
  chunk_id uuid references public.chunks(id) on delete set null,
  query_audit_id uuid references public.query_audits(id) on delete set null,

  provider text not null,
  model text not null,
  operation text not null,

  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  cached_tokens integer not null default 0,

  estimated_cost numeric(12,6),
  latency_ms integer,

  created_at timestamptz not null default now()
);

create index idx_token_usage_workspace_id on public.token_usage_log(workspace_id);
create index idx_token_usage_provider_model on public.token_usage_log(provider, model);
create index idx_token_usage_created_at on public.token_usage_log(created_at);
