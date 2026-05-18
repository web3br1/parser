create type source_authority_level as enum (
  'official',
  'normal',
  'informal'
);

create type source_reliability_level as enum (
  'high',
  'medium_high',
  'medium',
  'medium_low',
  'low',
  'very_low'
);

alter table public.sources
add column authority_level source_authority_level not null default 'normal',
add column source_reliability source_reliability_level not null default 'medium';

create index idx_sources_authority_level on public.sources(authority_level);
create index idx_sources_reliability on public.sources(source_reliability);
