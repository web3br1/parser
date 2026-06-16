# Industrial Parser Runbook

Status: proposed
Date: 2026-06-03

## Purpose

This runbook describes the first industrial/QMS parser flow for controlled
documents. It is an extension of the existing Context Compiler pipeline and
does not replace the generic MVP.

## Operator Flow

```text
upload controlled documents
-> file validation and quality gate
-> deterministic industrial metadata candidates
-> chunking with industrial structure hints
-> classification and schema-bound extraction
-> review document metadata
-> review revision/vigency decision
-> review facts, rules and relations
-> publish validated industrial context
-> export context_bundle.v1
```

## First-Slice Limits

Out of scope for this runbook:

- OCR for scanned PDFs;
- SharePoint, SoftExpert, Qualiex or other QMS/GED connectors;
- first-class top-level `graph` section in `context_bundle.v1`;
- chatbot/runtime behavior;
- semantic contradiction detection via embeddings.

OCR-required files should become gaps/readiness blockers instead of being
silently processed.

## Required Review Checks

Before industrial context can be published, review must confirm:

1. document code is present;
2. revision is present;
3. owner area is present;
4. vigent/obsolete status is justified by source text or review decision;
5. obsolete documents are not used as active operational rules;
6. relationships point to known document/process/form/role identifiers;
7. every industrial fact/rule/relation has evidence.

## Fixture Pack

Synthetic fixture pack:

```text
examples/industrial_qms
```

Smoke gate:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_qms_fixtures.py -q
```

Expected result:

```text
3 passed
```

## Focused Industrial Gate

```powershell
uv run --cache-dir .uv-cache pytest packages\domain\tests packages\parsers\tests packages\schema_registry\tests workers\classification\tests workers\extraction\tests tests\api\test_context_bundle.py tests\smoke\test_industrial_qms_fixtures.py -q
uv run --cache-dir .uv-cache ruff check packages apps workers tests
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Compatibility Gate

`context_bundle.v1` must remain strict and compatible:

```powershell
uv run --cache-dir .uv-cache pytest tests\compat\test_context_bundle_schema_export.py tests\compat\test_context_bundle_golden.py -q
uv run --cache-dir .uv-cache python scripts\context_bundle\export_json_schema.py --check
uv run --cache-dir .uv-cache python scripts\context_bundle\export_golden_bundle.py --check
```

If compatibility fails because a new top-level bundle field was added, stop and
write a separate bundle-version ADR before continuing.
