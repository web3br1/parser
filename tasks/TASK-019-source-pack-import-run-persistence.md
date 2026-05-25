# TASK-019 - Source Pack Import Run Persistence

Status: implemented locally, pending real Supabase smoke.

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

- Compile API should update the persisted run to `compiled` or `failed`
- ZIP/folder upload should create import runs automatically
- Console should show import-run history and latest bundle hash
- Real Supabase smoke should verify RLS, grants and audit access
