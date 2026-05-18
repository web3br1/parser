create table public.business_rules (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  source_id uuid not null references public.sources(id) on delete cascade,
  chunk_id uuid not null references public.chunks(id) on delete cascade,
  evidence_span_id uuid not null references public.evidence_spans(id) on delete restrict,

  rule_type text not null,
  schema_version text not null,

  condition jsonb not null,
  action jsonb not null,

  priority integer not null default 100,
  confidence numeric(5,4),
  status rule_status not null default 'extracted',

  valid_from timestamptz,
  valid_until timestamptz,

  supersedes uuid references public.business_rules(id) on delete set null,
  superseded_by uuid references public.business_rules(id) on delete set null,

  model_provider text,
  model_name text,
  prompt_version text,
  extraction_run_id uuid,

  created_by uuid references auth.users(id) on delete set null,
  reviewed_by uuid references auth.users(id) on delete set null,
  published_by uuid references auth.users(id) on delete set null,

  reviewed_at timestamptz,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint business_rules_confidence_range
    check (confidence is null or (confidence >= 0 and confidence <= 1))
);

create index idx_rules_workspace_id on public.business_rules(workspace_id);
create index idx_rules_source_id on public.business_rules(source_id);
create index idx_rules_chunk_id on public.business_rules(chunk_id);
create index idx_rules_type_status on public.business_rules(rule_type, status);
create index idx_rules_condition_gin on public.business_rules using gin(condition);
create index idx_rules_action_gin on public.business_rules using gin(action);

create trigger trg_business_rules_updated_at
before update on public.business_rules
for each row execute function public.touch_updated_at();
