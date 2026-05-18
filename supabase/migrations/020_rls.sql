alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.sources enable row level security;
alter table public.source_quality_reports enable row level security;
alter table public.chunks enable row level security;
alter table public.evidence_spans enable row level security;
alter table public.fact_type_schemas enable row level security;
alter table public.extracted_facts enable row level security;
alter table public.business_rules enable row level security;
alter table public.unknown_facts_queue enable row level security;
alter table public.contradictions enable row level security;
alter table public.validation_events enable row level security;
alter table public.query_audits enable row level security;
alter table public.processing_jobs enable row level security;
alter table public.token_usage_log enable row level security;
alter table public.audit_logs enable row level security;
alter table public.connector_instances enable row level security;
alter table public.api_specs enable row level security;
alter table public.mcp_tools enable row level security;
alter table public.mcp_tool_calls enable row level security;

-- Frontend access model: API-only.
-- Review/raw knowledge tables contain unpublished, unreviewed, or conflict data.
-- Browser clients must not read or mutate them directly through Supabase Data API;
-- the backend/API uses service_role and applies publication/review contracts.
revoke all on table public.chunks from anon;
revoke all on table public.chunks from authenticated;
grant all on table public.chunks to service_role;

revoke all on table public.evidence_spans from anon;
revoke all on table public.evidence_spans from authenticated;
grant all on table public.evidence_spans to service_role;

revoke all on table public.extracted_facts from anon;
revoke all on table public.extracted_facts from authenticated;
grant all on table public.extracted_facts to service_role;

revoke all on table public.business_rules from anon;
revoke all on table public.business_rules from authenticated;
grant all on table public.business_rules to service_role;

revoke all on table public.unknown_facts_queue from anon;
revoke all on table public.unknown_facts_queue from authenticated;
grant all on table public.unknown_facts_queue to service_role;

revoke all on table public.contradictions from anon;
revoke all on table public.contradictions from authenticated;
grant all on table public.contradictions to service_role;

create policy "members can view workspaces"
on public.workspaces
for select
using (public.is_workspace_member(id));

create policy "owners can update workspaces"
on public.workspaces
for update
using (public.has_workspace_role(id, array['owner']::workspace_role[]));

create policy "members can view workspace members"
on public.workspace_members
for select
using (public.is_workspace_member(workspace_id));

create policy "owners can manage workspace members"
on public.workspace_members
for all
using (public.has_workspace_role(workspace_id, array['owner']::workspace_role[]))
with check (public.has_workspace_role(workspace_id, array['owner']::workspace_role[]));

create policy "members can view sources"
on public.sources
for select
using (public.is_workspace_member(workspace_id));

create policy "managers can create sources"
on public.sources
for insert
with check (public.has_workspace_role(workspace_id, array['owner','manager']::workspace_role[]));

create policy "managers can update sources"
on public.sources
for update
using (public.has_workspace_role(workspace_id, array['owner','manager']::workspace_role[]));

create policy "members can view quality reports"
on public.source_quality_reports
for select
using (public.is_workspace_member(workspace_id));

create policy "reviewers can update facts"
on public.extracted_facts
for update
using (public.has_workspace_role(workspace_id, array['owner','manager','reviewer']::workspace_role[]));

create policy "reviewers can insert facts"
on public.extracted_facts
for insert
with check (public.has_workspace_role(workspace_id, array['owner','manager','reviewer']::workspace_role[]));

create policy "reviewers can update rules"
on public.business_rules
for update
using (public.has_workspace_role(workspace_id, array['owner','manager','reviewer']::workspace_role[]));

create policy "reviewers can insert rules"
on public.business_rules
for insert
with check (public.has_workspace_role(workspace_id, array['owner','manager','reviewer']::workspace_role[]));

create policy "reviewers can update unknown queue"
on public.unknown_facts_queue
for update
using (public.has_workspace_role(workspace_id, array['owner','manager','reviewer']::workspace_role[]));

create policy "reviewers can update contradictions"
on public.contradictions
for update
using (public.has_workspace_role(workspace_id, array['owner','manager','reviewer']::workspace_role[]));

create policy "managers can view validation events"
on public.validation_events
for select
using (public.has_workspace_role(workspace_id, array['owner','manager','reviewer']::workspace_role[]));

create policy "members can view own query audits"
on public.query_audits
for select
using (
  public.is_workspace_member(workspace_id)
  and (user_id = auth.uid() or public.has_workspace_role(workspace_id, array['owner','manager']::workspace_role[]))
);

create policy "owners can view audit logs"
on public.audit_logs
for select
using (public.has_workspace_role(workspace_id, array['owner','manager']::workspace_role[]));

create policy "managers can view connectors"
on public.connector_instances
for select
using (public.has_workspace_role(workspace_id, array['owner','manager']::workspace_role[]));

create policy "owners can manage connectors"
on public.connector_instances
for all
using (public.has_workspace_role(workspace_id, array['owner']::workspace_role[]))
with check (public.has_workspace_role(workspace_id, array['owner']::workspace_role[]));

create policy "managers can view mcp tools"
on public.mcp_tools
for select
using (
  workspace_id is null
  or public.has_workspace_role(workspace_id, array['owner','manager']::workspace_role[])
);

create policy "managers can view mcp calls"
on public.mcp_tool_calls
for select
using (public.has_workspace_role(workspace_id, array['owner','manager']::workspace_role[]));
