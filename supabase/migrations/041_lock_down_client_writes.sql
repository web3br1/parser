drop policy if exists "owners can update workspaces" on public.workspaces;
drop policy if exists "owners can manage workspace members" on public.workspace_members;
drop policy if exists "managers can create sources" on public.sources;
drop policy if exists "managers can update sources" on public.sources;

-- Browser writes must go through the API/service role so validation, storage
-- coupling, job idempotency, and audit behavior cannot be bypassed.
revoke insert, update, delete on table public.workspaces from anon;
revoke insert, update, delete on table public.workspaces from authenticated;
revoke insert, update, delete on table public.workspace_members from anon;
revoke insert, update, delete on table public.workspace_members from authenticated;
revoke insert, update, delete on table public.sources from anon;
revoke insert, update, delete on table public.sources from authenticated;

grant all on table public.workspaces to service_role;
grant all on table public.workspace_members to service_role;
grant all on table public.sources to service_role;
