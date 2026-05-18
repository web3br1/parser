alter table public.unknown_facts_queue
add column if not exists metadata jsonb not null default '{}'::jsonb;
