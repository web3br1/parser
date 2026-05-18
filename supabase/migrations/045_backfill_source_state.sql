select public.finalize_source_state_after_extraction(id, workspace_id)
from public.sources
where status in ('processing', 'extracted', 'needs_review');
