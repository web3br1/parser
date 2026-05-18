-- Lock down default function execution grants.
-- Worker/business RPCs are SECURITY DEFINER and must only be callable by service_role.

revoke execute on all functions in schema public from public;
revoke execute on all functions in schema public from anon;
revoke execute on all functions in schema public from authenticated;

alter default privileges in schema public revoke execute on functions from public;
alter default privileges in schema public revoke execute on functions from anon;
alter default privileges in schema public revoke execute on functions from authenticated;

grant execute on function public.is_workspace_member(uuid) to authenticated;
grant execute on function public.has_workspace_role(uuid, workspace_role[]) to authenticated;
grant execute on function public.has_workspace_role_for_user(uuid, uuid, workspace_role[]) to authenticated;
grant execute on function public.storage_workspace_id(text) to authenticated;

grant execute on all functions in schema public to service_role;
alter default privileges in schema public grant execute on functions to service_role;
