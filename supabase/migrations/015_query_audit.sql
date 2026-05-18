create table public.query_audits (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,

  question text not null,
  answer text,
  answer_state answer_state not null,

  facts_used uuid[] not null default '{}',
  rules_used uuid[] not null default '{}',
  sources_used uuid[] not null default '{}',

  used_unvalidated_data boolean not null default false,
  confidence numeric(5,4),

  model_provider text,
  model_name text,
  prompt_version text,

  latency_ms integer,
  token_input integer,
  token_output integer,
  estimated_cost numeric(12,6),

  created_at timestamptz not null default now(),

  constraint query_audit_confidence_range
    check (confidence is null or (confidence >= 0 and confidence <= 1))
);

create index idx_query_audits_workspace_id on public.query_audits(workspace_id);
create index idx_query_audits_user_id on public.query_audits(user_id);
create index idx_query_audits_answer_state on public.query_audits(answer_state);
create index idx_query_audits_created_at on public.query_audits(created_at);
