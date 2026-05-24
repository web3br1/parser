# TASK-011 - Context Bundle Integration

Status: done

## Objective

Integrate the clean Context Bundle implementation as the canonical bridge
between this local extractor and the external chatbot project.

## Scope

- Add `context_bundle.v1` schemas, service, API route and audit behavior.
- Export only published sources, published facts, published rules and evidence
  spans explicitly referenced by selected records.
- Compute deterministic `context_version` and `integrity.bundle_hash`.
- Block readiness for open unknowns, open/needs_review contradictions, missing
  published source provenance and empty published knowledge.
- Sanitize exported payloads and evidence so secrets, signed URLs, raw prompts,
  provider responses, stack traces, local paths and unpublished content never
  leave the project.
- Document the contract in `docs/03-pipeline/CONTEXT_BUNDLE.md`.

## Production Constraints

- Context export is not a chatbot answer.
- Export must not mutate the consuming runtime.
- Every successful export must write `audit_logs.action =
  'context_bundle.export'`.
- Future persisted publishing remains owner/manager only.

## Verification

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py tests\api\test_knowledge.py -q
uv run --cache-dir .uv-cache ruff check apps\api\src\context_builder tests\api\test_context_bundle.py
```

Implemented in commit `10f1c14`.
