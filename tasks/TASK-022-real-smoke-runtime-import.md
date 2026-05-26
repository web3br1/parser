# TASK-022 - Real Smoke + Runtime Import Proof

Status: planned

## Goal

Prove the Context Compiler flow against the real Docker/Supabase runtime and a
consumer runtime that imports `context_bundle.v1` without manual editing.

## Scope

- Apply migrations through `047` in a real Supabase/local Docker environment.
- Validate RLS/grants for `context_build_runs` and legacy
  `source_pack_import_runs`.
- Run the canonical real smoke orchestrator.
- Compile the compounding pharmacy gold source pack.
- Import the generated `context_bundle.v1` into the external runtime.
- Verify answers cite evidence and respect blockers/warnings.

## Acceptance

- `context_build_runs` is backend-owned and inaccessible to browser roles unless
  intentionally exposed later.
- Source-pack preflight/compile lifecycle writes auditably.
- Bundle readiness is `warning` for synthetic pack, not `blocked`.
- Bundle hash is deterministic across repeated runs.
- Runtime imports the bundle without manual edits.
- Runtime answer uses cited evidence and refuses forbidden behavior.
- Smoke output is saved with date, commit SHA and environment name, without
  secrets.

## Verification Target

```powershell
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --json-report .run\smoke-local-full.json
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py --source-dir C:\tmp\context-builder-sources\compounding-pharmacy-gold --check
```

The runtime import command belongs to the consumer runtime repo and must be
recorded here after it is selected.
