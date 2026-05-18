create table public.fact_type_schemas (
  id uuid primary key default gen_random_uuid(),

  fact_type text not null,
  schema_version text not null,
  status text not null default 'draft',

  json_schema jsonb not null,
  pydantic_schema_ref text,
  extraction_prompt text,
  normalization_policy jsonb not null default '{}'::jsonb,
  validation_policy jsonb not null default '{}'::jsonb,

  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique(fact_type, schema_version),

  check (status in ('draft', 'active', 'deprecated'))
);

create index idx_fact_type_schemas_fact_type
  on public.fact_type_schemas(fact_type);

create index idx_fact_type_schemas_status
  on public.fact_type_schemas(status);

create trigger trg_fact_type_schemas_updated_at
before update on public.fact_type_schemas
for each row execute function public.touch_updated_at();
