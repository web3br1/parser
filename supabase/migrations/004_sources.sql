create table public.sources (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,

  type source_type not null,
  status source_status not null default 'draft',

  title text,
  original_filename text,
  storage_bucket text,
  storage_path text,

  external_url text,
  external_provider text,
  external_id text,

  mime_type text,
  file_size_bytes bigint,
  file_hash text,

  source_version integer not null default 1,
  metadata jsonb not null default '{}'::jsonb,

  uploaded_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create index idx_sources_workspace_id on public.sources(workspace_id);
create index idx_sources_status on public.sources(status);
create index idx_sources_type on public.sources(type);
create index idx_sources_file_hash on public.sources(file_hash);

create trigger trg_sources_updated_at
before update on public.sources
for each row execute function public.touch_updated_at();
