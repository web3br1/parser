insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'context-builder-private',
  'context-builder-private',
  false,
  104857600,
  array[
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain',
    'text/csv'
  ]
)
on conflict (id) do update
set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create or replace function public.storage_workspace_id(object_name text)
returns uuid
language sql
stable
as $$
  select case
    when split_part(object_name, '/', 1) = 'workspaces'
      and split_part(object_name, '/', 2) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    then split_part(object_name, '/', 2)::uuid
    else null
  end;
$$;

create policy "managers can upload private workspace files"
on storage.objects
for insert
with check (
  bucket_id = 'context-builder-private'
  and split_part(name, '/', 1) = 'workspaces'
  and split_part(name, '/', 3) = 'sources'
  and public.has_workspace_role(
    public.storage_workspace_id(name),
    array['owner','manager']::workspace_role[]
  )
);

create policy "managers can update private workspace files"
on storage.objects
for update
using (
  bucket_id = 'context-builder-private'
  and public.has_workspace_role(
    public.storage_workspace_id(name),
    array['owner','manager']::workspace_role[]
  )
)
with check (
  bucket_id = 'context-builder-private'
  and public.has_workspace_role(
    public.storage_workspace_id(name),
    array['owner','manager']::workspace_role[]
  )
);

create policy "owners can delete private workspace files"
on storage.objects
for delete
using (
  bucket_id = 'context-builder-private'
  and public.has_workspace_role(
    public.storage_workspace_id(name),
    array['owner']::workspace_role[]
  )
);
