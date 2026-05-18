-- Security grants for SECURITY DEFINER functions.
--
-- Worker RPCs (complete_ingest_job, complete_classification_job,
-- complete_extraction_job, get_or_create_processing_job) have NO internal
-- authorization checks — they trust the caller. They must only be callable
-- by service_role (workers and API backend), never by authenticated users.
--
-- RLS helper functions need authenticated because they are invoked by RLS
-- policy expressions during query evaluation in the authenticated role context.

revoke execute on all functions in schema public from public;
revoke execute on all functions in schema public from anon;
revoke execute on all functions in schema public from authenticated;

-- RLS helpers only: needed for row-level security policy evaluation.
grant execute on function public.is_workspace_member(uuid) to authenticated;
grant execute on function public.has_workspace_role(uuid, workspace_role[]) to authenticated;
grant execute on function public.has_workspace_role_for_user(uuid, uuid, workspace_role[]) to authenticated;

-- Storage policy helper: used by Supabase storage RLS.
grant execute on function public.storage_workspace_id(text) to authenticated;

-- All business and worker RPCs: service_role only.
-- service_role bypasses RLS by default in Supabase, but explicit grants are
-- required for SECURITY DEFINER functions to be callable from the API and workers.
grant execute on all functions in schema public to service_role;
