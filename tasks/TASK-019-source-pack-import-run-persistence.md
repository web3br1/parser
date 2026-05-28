# TASK-019 - Source Pack Import Run Persistence

Status: implemented and committed; pending real Supabase smoke.

## Goal

Persist every source-pack preflight and compile lifecycle event as an auditable
workspace-scoped import run.

## Implemented

- Migration `046_source_pack_import_runs.sql`
- Backend-owned table grants for `source_pack_import_runs`
- Pydantic schemas for import run create/update/response
- Service to create preflight runs and update compiled runs
- Deterministic `input_hash` for source-pack directory contents
- Optional `persist` flag on source-pack preflight API
- `import_run_id` returned when persistence is requested

## Remaining Product Work

- New builds should use canonical `context_build_runs` from `TASK-020`.
- `source_pack_import_runs` remains compatibility/history for the legacy
  source-pack route.
- ZIP/folder upload staging should create canonical context build runs
  automatically; tracked in `TASK-021`.
- Real Supabase smoke should verify RLS, grants and audit access; tracked in
  `TASK-022`.
