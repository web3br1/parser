create table public.chunks (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  source_id uuid not null references public.sources(id) on delete cascade,

  chunk_index integer not null,
  status chunk_status not null default 'pending',

  content text not null,
  content_hash text not null,

  page_start integer,
  page_end integer,

  sheet_name text,
  row_start integer,
  row_end integer,

  section_title text,
  token_count integer,

  classification jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique(source_id, chunk_index)
);

create index idx_chunks_workspace_id on public.chunks(workspace_id);
create index idx_chunks_source_id on public.chunks(source_id);
create index idx_chunks_status on public.chunks(status);
create index idx_chunks_content_hash on public.chunks(content_hash);
create index idx_chunks_content_trgm on public.chunks using gin (content gin_trgm_ops);

create trigger trg_chunks_updated_at
before update on public.chunks
for each row execute function public.touch_updated_at();
