create type workspace_role as enum (
  'owner',
  'manager',
  'reviewer',
  'staff'
);

create type workspace_status as enum (
  'active',
  'limited',
  'suspended',
  'deleted'
);

create type source_type as enum (
  'upload',
  'url',
  'manual_text',
  'api_connector',
  'mcp_connector'
);

create type source_status as enum (
  'draft',
  'uploaded',
  'quality_checked',
  'processing',
  'needs_review',
  'published',
  'failed',
  'deprecated',
  'deleted'
);

create type chunk_status as enum (
  'pending',
  'classified',
  'extracted',
  'needs_review',
  'approved',
  'rejected',
  'failed'
);

create type fact_status as enum (
  'extracted',
  'needs_review',
  'approved',
  'published',
  'rejected',
  'deprecated',
  'superseded',
  'conflicted'
);

create type rule_status as enum (
  'extracted',
  'needs_review',
  'approved',
  'published',
  'rejected',
  'deprecated',
  'superseded',
  'conflicted'
);

create type validation_action as enum (
  'approved',
  'edited',
  'rejected',
  'published',
  'deprecated',
  'superseded',
  'conflict_marked',
  'manual_created'
);

create type job_status as enum (
  'queued',
  'running',
  'succeeded',
  'failed',
  'cancelled',
  'retrying'
);

create type answer_state as enum (
  'valid_answer',
  'not_found',
  'conflicting_sources',
  'needs_human_validation',
  'partial_answer'
);

create type risk_level as enum (
  'low',
  'medium',
  'high',
  'critical'
);
