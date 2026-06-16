# Industrial Metadata Pattern Expansion SDD Plan

Date: 2026-06-03
Branch: `codex/industrial-parser-partials`
Task: `TASK-025-industrial-metadata-pattern-expansion`

## Objective

Raise deterministic metadata quality on the real dirty-document benchmark by
closing the document-code misses identified in TASK-024 without inflating
quality through unsafe false positives.

## Current Evidence

TASK-024 baseline:

- parsed documents: 5/5;
- split-page fallback: 1 document;
- missing document code: 5;
- missing revision: 2;
- expected-code misses: `POP-O-SNVS-010`, `BLU002`, `POP 005`,
  `PTC.DEPQI-SCIRAS.001`.

## Implementation Strategy

1. Add red unit tests for the real code patterns.
2. Add conservative parser support for:
   - multi-segment POP codes;
   - compact header/filename codes;
   - spaced POP codes;
   - dotted protocol codes with dash segments.
3. Add regression tests for false positives:
   - table-of-contents section code `POP 101`;
   - BLU table row not becoming `owner_area`.
4. Regenerate the local real benchmark.
5. Update benchmark docs and task evidence.

## Acceptance

- `packages\parsers\tests\test_industrial_metadata.py` passes.
- `tests\smoke\test_industrial_dirty_benchmark.py` passes.
- `missing_document_code` falls to 1 on `.run\industrial-real`.
- `missing_revision` falls to 1 on `.run\industrial-real` by accepting explicit
  protocol version labels.
- Expected-code findings are empty.
- PMPR remains explicitly incomplete.

## Multi-Agent Notes

- Orchestrator validated scope, risks and gates.
- Task worker added the red metadata tests and confirmed failure.
- Main agent implemented and integrated the parser changes.
- Reviewer and approval run after verification gates.
