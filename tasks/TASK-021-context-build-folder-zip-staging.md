# TASK-021 - Context Build Folder/ZIP Staging

Status: planned

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
