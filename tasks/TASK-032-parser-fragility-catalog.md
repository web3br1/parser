# TASK-032 - Parser Fragility Catalog

Status: completed

## Goal

Create a project-level catalog of parser fragilities that turns quality
concerns into explicit, testable failure hypotheses.

## Background

The current Parser benchmark stack proves that documents can be processed and
that diagnostic objects are emitted. The next quality gap is directional: the
project needs a reliable way to name the ways the parser can lie, overclaim,
miss evidence or create review noise before new implementation work starts.

This task is not a benchmark rewrite. It creates the management layer that
drives TDD: each fragility must be small enough to reproduce, severe enough to
rank and concrete enough to become a red test.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Owns the fragility taxonomy and rejects vague quality goals |
| Task Worker | Creates the catalog, seeds concrete entries and links each entry to a planned test layer |
| Reviewer | Checks that every entry is testable, scoped and free of metric theater |
| Approval | Runs documentation validation, placeholder scan and secret scan |

## Scope

- Define a stable fragility record shape with:
  - `fragility_id`;
  - affected layer;
  - severity;
  - failure hypothesis;
  - minimal reproducer idea;
  - expected red test;
  - expected negative/adversarial assertion;
  - expected benchmark signal;
  - current status.
- Seed the first catalog from known Parser risks:
  - file-level metadata promoted from nested/multi-document content;
  - table of contents text promoted as requirements;
  - recurring headers or footers contaminating sections;
  - visual content described as understood when only references exist;
  - section hierarchy gaps creating noisy review packets;
  - evidence quotes or page spans drifting away from source text;
  - OCR-required pages passing as clean text extraction;
  - large PDF split fallback losing diagnostic fidelity.
- Define allowed statuses:
  - `discovered`;
  - `red_test_written`;
  - `fixed`;
  - `benchmarked`;
  - `accepted`;
  - `known_limit`.
- Define allowed severity levels:
  - `critical_publication_risk`;
  - `high_review_risk`;
  - `medium_quality_risk`;
  - `low_diagnostic_risk`.
- Keep the catalog independent from Hermes, Tri-Memory and agent memory flows.

## Out Of Scope

- Parser implementation changes.
- New extraction rules.
- New benchmark scoring.
- CI enforcement.
- UI changes.
- Runtime app changes.
- Hermes, Tri-Memory or agent infrastructure repair.

## Proposed Files

- Create: `docs/07-qa/PARSER_FRAGILITY_CATALOG.md`
- Create: `tests/smoke/test_parser_fragility_catalog.py`
- Modify: `tasks/TASK-032-parser-fragility-catalog.md`

## Acceptance

- The catalog defines a reusable fragility record format.
- At least eight seed fragilities are recorded.
- Each seed fragility has a concrete red-test target.
- Each seed fragility has at least one negative or adversarial assertion.
- Each seed fragility names the benchmark signal it should later influence.
- No entry uses generic wording such as "make parser better" without a specific
  failure hypothesis.
- The smoke test fails if a catalog entry misses required fields or uses an
  unknown status/severity.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_catalog.py -q
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [x] Add a red smoke test for catalog schema requirements.
- [x] Create the initial fragility catalog document.
- [x] Seed known Parser fragilities from TASK-024 through TASK-031.
- [x] Add allowed status and severity validation.
- [x] Run the verification target.
- [x] Record execution evidence in this task file.

## Execution Evidence

Completed on 2026-06-06.

TDD red:

```text
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_catalog.py -q
2 failed because docs/07-qa/PARSER_FRAGILITY_CATALOG.md was missing.
```

TDD green:

```text
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_catalog.py -q
2 passed in 0.02s.
```

Final verification:

```text
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_catalog.py -q
2 passed in 0.02s.

uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
exit 0 with only SSL_CERT_DIR warnings.
```
