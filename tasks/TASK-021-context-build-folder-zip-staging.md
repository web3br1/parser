# TASK-021 - Context Build Folder/ZIP Staging

Status: implemented

## Goal

Let the user upload a folder or zip through the unified Context Build Wizard and
stage the actual source bytes on the backend before preflight/compile. This
removes the current local-dev dependency on server `source_dir` for browser
uploads.

## Non-Negotiable Architecture

- Backend remains the authoritative detector.
- Frontend preview remains optimistic only.
- Browser must not send arbitrary server paths.
- Public APIs should use `staged_upload_id`, not `source_dir`.
- Any server-side path resolution must stay under a configured staging root.
- Mutating actions require upload/build permission.

## Scope

- Add a staging API for multi-file/folder/zip uploads.
- Persist staged upload metadata and deterministic `input_hash`.
- Link staged uploads to canonical `context_build_runs`.
- Make source-pack compile resolve from `staged_upload_id`.
- Keep legacy `source_dir` only for local/dev and tests, guarded by allowlist.
- Update the Wizard so `Generate Bundle` has a happy path after staging.

## Acceptance

- Folder containing `00_source_manifest.md` can be selected in the Wizard,
  staged by the backend, preflighted as `source_pack`, and compiled without
  manual path configuration.
- Zip with the same content follows the same lifecycle.
- Loose files stage and preflight as `single_document` or `multi_document_batch`
  without being marked as source pack.
- Blocked extensions/secrets are rejected before compile.
- API responses never expose private server paths.
- Tests cover path traversal, zip slip, duplicate staged input, and missing
  manifest files.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_build_runs.py tests\api\test_context_build_staging.py -q
corepack pnpm --filter @context-builder/web build
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Implementation Notes

- Added `POST /workspaces/{workspace_id}/context-build-runs/staged-uploads`
  for folder, multi-file, and zip staging.
- Backend preflight remains authoritative and resolves source-pack candidates
  from `staged_upload_id`.
- Wizard now stages real file bytes before preflight and does not send server
  paths from the browser.
- Compile resolves staged source packs from the staging root and returns a
  public `staged_upload:<id>/<file>` output reference instead of a private path.
- Tests cover folder staging, zip staging, path traversal, zip slip, duplicate
  zip entries, unreadable zip entries, upload limits, rejected source-pack
  compile blocking, and sensitive frontend preview blockers.

## Verified 2026-05-26

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_build_staging.py tests\api\test_context_build_runs.py -q
# 24 passed

node apps\web\scripts\test-context-build.mjs
# passed

corepack pnpm --filter @context-builder/web typecheck
# passed

npm run typecheck:python:strict-full
# passed
```
