# TASK-035 - Parser Invariant Test Harness

Status: done

## Goal

Create invariant tests that enforce parser laws across fixtures and outputs,
independent of individual extraction rules.

## Background

Negative tests catch named fragilities. Invariants catch whole classes of
mistakes that should never be allowed: evidence quotes that do not exist in
source text, page spans outside the document, review packets without reasons,
unknown risk codes and diagnostics that delete source text to look cleaner.

This task adds a harness that turns those laws into repeatable tests.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Defines project-level parser laws and blocks vague invariants |
| Task Worker | Writes failing invariant tests and implements reusable test helpers |
| Reviewer | Checks that invariants test behavior instead of implementation details |
| Approval | Runs parser tests, fixture smoke tests, lint, type checks and secret scan |

## Scope

- Add invariants for evidence:
  - every candidate quote must exist in source text after parser sanitation;
  - every evidence page must be within the parsed page range.
- Add invariants for chunks:
  - chunk source spans must be stable and non-empty;
  - section path metadata must not change text hashes;
  - chunk page spans must be ordered.
- Add invariants for diagnostics:
  - risk codes must come from known parser vocabularies;
  - diagnostics must not remove source text from extraction results.
- Add invariants for review packets:
  - every packet has a stable ID, reason code, severity and suggested decision;
  - every packet has evidence or an explicit document-level reason;
  - packet counts are bounded for repeated equivalent risks.
- Run invariants over parser fragility fixtures and targeted synthetic results.

## Out Of Scope

- New parser features.
- New benchmark score model.
- Real PDF corpus expansion.
- UI changes.
- Runtime app changes.
- Hermes, Tri-Memory or agent infrastructure repair.

## Proposed Files

- Create: `packages/parsers/tests/test_industrial_invariants.py`
- Create: `packages/parsers/tests/industrial_invariant_helpers.py`
- Modify: `packages/parsers/tests/test_industrial_negative_adversarial.py`
- Modify: `tasks/TASK-035-parser-invariant-test-harness.md`

## Acceptance

- Invariant tests fail on deliberately malformed parser objects.
- Invariant tests pass for valid parser outputs.
- Invariants run against parser fragility fixtures.
- Unknown risk codes are rejected by tests.
- Evidence quote and page-span drift are detected.
- Review packet shape and bounded grouping are enforced.
- Helpers remain test-only and do not add test-only methods to production code.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_invariants.py -q
uv run --cache-dir .uv-cache pytest packages\parsers\tests -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_fixtures.py -q
uv run --cache-dir .uv-cache ruff check packages\parsers tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [x] Add red tests for invalid evidence quote drift.
- [x] Add red tests for invalid page spans.
- [x] Add red tests for unknown risk codes.
- [x] Add red tests for review packet shape.
- [x] Add reusable invariant helpers under parser tests.
- [x] Run invariants against parser fragility fixtures.
- [x] Run the verification target.
- [x] Record execution evidence in this task file.

## Execution Evidence

- Red: `uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_invariants.py -q` failed as expected before helper implementation with `ModuleNotFoundError: No module named 'packages.parsers.tests.industrial_invariant_helpers'`.
- Follow-up red: `uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_invariants.py -q` failed with 5 expected failures for unsupported/empty evidence collections, page spans without parsed pages, anchorless review evidence and generator-hidden unknown risk codes.
- Green focused: `uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_invariants.py -q` -> `25 passed in 0.08s`.
- Parser suite: `uv run --cache-dir .uv-cache pytest packages\parsers\tests -q` -> `129 passed in 0.61s`.
- Fixture smoke: `uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_fixtures.py -q` -> `5 passed in 0.01s`.
- Ruff: `uv run --cache-dir .uv-cache ruff check packages\parsers tests` -> `All checks passed!`.
- Mypy: `uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers` -> `Success: no issues found in 16 source files`.
- Secret scan: `uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py` -> exit code 0, no findings printed.
