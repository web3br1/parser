create view public.published_facts
with (security_invoker = true)
as
select f.*
from public.extracted_facts f
join public.sources s
  on s.id = f.source_id
 and s.workspace_id = f.workspace_id
where f.status = 'published'
  and f.superseded_by is null
  and (f.valid_from is null or f.valid_from <= now())
  and (f.valid_until is null or f.valid_until >= now())
  and s.status = 'published'
  and s.deleted_at is null;

create view public.published_rules
with (security_invoker = true)
as
select r.*
from public.business_rules r
join public.sources s
  on s.id = r.source_id
 and s.workspace_id = r.workspace_id
where r.status = 'published'
  and r.superseded_by is null
  and (r.valid_from is null or r.valid_from <= now())
  and (r.valid_until is null or r.valid_until >= now())
  and s.status = 'published'
  and s.deleted_at is null;

create view public.published_sources
with (security_invoker = true)
as
select *
from public.sources
where status = 'published'
  and deleted_at is null;
