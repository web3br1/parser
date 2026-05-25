# TASK-018 - Source Pack Preflight API

Status: implemented locally, pending full product upload UX.

## Goal

Detect whether an uploaded/extracted folder is a complete source pack before
processing files individually.

## Implemented

- Endpoint:
  `POST /workspaces/{workspace_id}/sources/source-pack/preflight`
- Request:
  `{"source_dir": "C:\\tmp\\context-builder-sources\\compounding-pharmacy-gold"}`
- Response includes:
  - `is_source_pack`
  - `status`
  - `recommended_action`
  - source pack id/version/language/publication status
  - numbered source count
  - CSV/Markdown counts
  - manifest document/reference counts
  - missing and extra files
  - errors

## Behavior

- Complete pack: `recommended_action = compile_as_source_pack`
- No manifest: `recommended_action = normal_ingest`
- Missing/extra manifest files: `recommended_action = reject`
- Invalid directory/manifest: `recommended_action = reject`

## Verification

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_source_pack_preflight.py -q
```
