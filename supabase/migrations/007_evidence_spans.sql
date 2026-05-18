create table public.evidence_spans (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  source_id uuid not null references public.sources(id) on delete cascade,
  chunk_id uuid not null references public.chunks(id) on delete cascade,

  quote text not null,
  quote_hash text not null,

  char_start integer,
  char_end integer,

  page_number integer,
  sheet_name text,
  row_number integer,
  column_name text,

  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now()
);

create index idx_evidence_workspace_id on public.evidence_spans(workspace_id);
create index idx_evidence_source_id on public.evidence_spans(source_id);
create index idx_evidence_chunk_id on public.evidence_spans(chunk_id);
create index idx_evidence_quote_hash on public.evidence_spans(quote_hash);
