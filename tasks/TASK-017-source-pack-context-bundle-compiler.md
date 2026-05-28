# TASK-017 - Source Pack Context Bundle Compiler

Status: implemented and committed; pending runtime import smoke.

## Goal

Compile a normalized source pack into `context_bundle.v1` without requiring the
user to manually map files, rows, sections or evidence anchors.

## Implemented

- New workspace package: `packages/source_pack`.
- Manifest parser for `00_source_manifest.md`.
- Numbered source discovery excluding manifest and README.
- CSV reader preserving source row numbers.
- Markdown section evidence extraction.
- Deterministic UUID v5 IDs for sources, facts, rules and evidence.
- Compilation of facts, rules, gaps, tests, memory policy and tool
  recommendations.
- Readiness with synthetic-pack warnings instead of production activation.
- Sanitization for bearer tokens, local private paths, raw prompts, provider
  responses and stack traces.
- Deterministic bundle hash compatible with `ContextBundleResponse`.
- CLI: `scripts/source_pack/compile_context_bundle.py`.
- Compat test for the compounding pharmacy gold pack.

## Remaining Product Work

- Browser folder/zip staging is tracked in `TASK-021`.
- Runtime import smoke using the generated artifact is tracked in `TASK-022`.

The source-pack preflight API, import-run persistence and unified Context Build
Wizard are implemented in `TASK-018`, `TASK-019` and `TASK-020`.

## Verification

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests -q
uv run --cache-dir .uv-cache pytest tests\compat\test_compounding_pharmacy_source_pack_compiler.py -q
```
