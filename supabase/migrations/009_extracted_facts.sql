create table public.extracted_facts (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  source_id uuid not null references public.sources(id) on delete cascade,
  chunk_id uuid not null references public.chunks(id) on delete cascade,
  evidence_span_id uuid references public.evidence_spans(id) on delete set null,

  fact_type text not null,
  schema_version text not null,

  content jsonb not null,
  normalized_content jsonb not null default '{}'::jsonb,

  confidence numeric(5,4),
  status fact_status not null default 'extracted',

  valid_from timestamptz,
  valid_until timestamptz,

  supersedes uuid references public.extracted_facts(id) on delete set null,
  superseded_by uuid references public.extracted_facts(id) on delete set null,

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

  constraint extracted_facts_confidence_range
    check (confidence is null or (confidence >= 0 and confidence <= 1))
);

create index idx_facts_workspace_id on public.extracted_facts(workspace_id);
create index idx_facts_source_id on public.extracted_facts(source_id);
create index idx_facts_chunk_id on public.extracted_facts(chunk_id);
create index idx_facts_type_status on public.extracted_facts(fact_type, status);
create index idx_facts_content_gin on public.extracted_facts using gin(content);
create index idx_facts_normalized_gin on public.extracted_facts using gin(normalized_content);

create trigger trg_extracted_facts_updated_at
before update on public.extracted_facts
for each row execute function public.touch_updated_at();
