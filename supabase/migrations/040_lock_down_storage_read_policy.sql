drop policy if exists "members can read private workspace files" on storage.objects;

-- Original workspace files are API-only. Application endpoints may proxy
-- authorized reads through service role after audit/logging and redaction checks.
