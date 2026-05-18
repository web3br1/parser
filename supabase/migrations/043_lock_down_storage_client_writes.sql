drop policy if exists "managers can upload private workspace files" on storage.objects;
drop policy if exists "managers can update private workspace files" on storage.objects;
drop policy if exists "owners can delete private workspace files" on storage.objects;

-- Storage writes must go through the API/service role. Direct browser writes to
-- storage bypass file validation, source/job creation, audit behavior, and LGPD
-- storage-delete accounting.
