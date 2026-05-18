create table public.connector_instances (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,

  provider text not null,
  auth_type text not null,
  status text not null default 'active',

  external_account_id text,
  scopes text[] not null default '{}',

  token_secret_ref text,
  last_sync_at timestamptz,
  next_sync_at timestamptz,

  error_message text,
  metadata jsonb not null default '{}'::jsonb,

  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  check (auth_type in ('oauth', 'api_key', 'none')),
  check (status in ('active', 'error', 'expired', 'revoked', 'disabled'))
);

create table public.api_specs (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid references public.workspaces(id) on delete cascade,

  provider text not null,
  spec_url text,
  spec_hash text not null,
  raw_spec jsonb not null,

  status text not null default 'imported',

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique(provider, spec_hash)
);

create table public.mcp_tools (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid references public.workspaces(id) on delete cascade,
  api_spec_id uuid references public.api_specs(id) on delete cascade,

  provider text not null,
  tool_name text not null,
  original_operation_id text,

  method text not null,
  path text not null,

  input_schema jsonb not null default '{}'::jsonb,
  output_schema jsonb not null default '{}'::jsonb,

  risk risk_level not null default 'medium',
  risk_category text not null default 'unsupported',

  enabled boolean not null default false,
  requires_human_approval boolean not null default true,

  max_calls_per_hour integer not null default 60,
  allowed_roles workspace_role[] not null default array['owner']::workspace_role[],

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique(provider, tool_name)
);

create table public.mcp_tool_calls (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  tool_id uuid not null references public.mcp_tools(id) on delete restrict,
  user_id uuid references auth.users(id) on delete set null,

  input_hash text,
  output_hash text,

  status text not null,
  latency_ms integer,
  error_message text,

  created_at timestamptz not null default now()
);

create index idx_connectors_workspace_id on public.connector_instances(workspace_id);
create index idx_mcp_tools_provider on public.mcp_tools(provider);
create index idx_mcp_tools_enabled on public.mcp_tools(enabled);
create index idx_mcp_calls_workspace_id on public.mcp_tool_calls(workspace_id);
create index idx_mcp_calls_tool_id on public.mcp_tool_calls(tool_id);

create trigger trg_connector_instances_updated_at
before update on public.connector_instances
for each row execute function public.touch_updated_at();

create trigger trg_api_specs_updated_at
before update on public.api_specs
for each row execute function public.touch_updated_at();

create trigger trg_mcp_tools_updated_at
before update on public.mcp_tools
for each row execute function public.touch_updated_at();
