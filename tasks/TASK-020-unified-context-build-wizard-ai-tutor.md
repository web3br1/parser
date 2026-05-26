# TASK-020 - Unified Context Build Wizard + AI Tutor

**Status:** implemented locally on branch `codex/source-pack-context-bundle-compiler`

## Goal

Create one Context Build flow for single documents, loose multi-document batches
and source packs. The user should not need to know whether an upload is a source
pack; backend preflight is authoritative and the frontend only shows an
optimistic preview.

## Implemented

- `context_build_runs` migration `047` with backend-owned access, indexes,
  `input_fingerprint`, nullable `input_hash`, readiness fields and updated-at
  trigger.
- Domain model vocabulary for `ContextBuildRun`, modes, statuses and
  recommended actions.
- Backend canonical context build API:
  - `POST /workspaces/{workspace_id}/context-build-runs/preflight`
  - `POST /workspaces/{workspace_id}/context-build-runs`
  - `GET /workspaces/{workspace_id}/context-build-runs`
  - `GET /workspaces/{workspace_id}/context-build-runs/{run_id}`
  - `POST /workspaces/{workspace_id}/context-build-runs/{run_id}/actions/compile`
- Source-pack compile action for runs with server-accessible `source_dir`.
- `source_dir` is treated as an internal server path: it must resolve under
  `CONTEXT_BUILD_ALLOWED_SOURCE_ROOTS` or the default local source root, and it
  is excluded from API responses.
- Browser metadata detection of source pack candidates via
  `00_source_manifest.md`, with explicit `source_pack_staging_required` blocker
  when content is not staged on the backend.
- Frontend route `/workspaces/{workspaceId}/context-build` with a Wizard for
  select, detect, preflight, build, review/publish, generate bundle and final
  readiness.
- AI tutor API sidecar with allowlisted deterministic tools and confirmation
  required for mutating compile requests.
- Tutor compile is wired to the canonical context build compile use case and
  validates a workspace/run/tool-bound confirmation token.

## Not Implemented In This Slice

- Direct browser folder/zip upload staging for source-pack compilation.
- Normal document and loose batch compilation into bundle without the existing
  review/publish pipeline.
- LLM-backed freeform tutorial conversation. Current tutor is deterministic by
  design.

## Verification

- `uv run --cache-dir .uv-cache pytest tests\api\test_context_build_runs.py tests\api\test_context_build_tutor.py packages\domain\tests\test_context_build_models.py tests\integrity\test_context_build_runs_migration.py -q`
- `node apps\web\scripts\test-context-build.mjs`
- `uv run --cache-dir .uv-cache ruff check ...`
- `npm run typecheck:python`
- `corepack pnpm --filter @context-builder/web typecheck`
