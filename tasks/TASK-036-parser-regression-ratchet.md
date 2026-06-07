# TASK-036 - Parser Regression Ratchet

Status: completed

## Goal

Create a regression ratchet that compares current parser quality signals
against an accepted baseline and blocks silent quality drift.

## Background

Once fragility tests and invariants exist, the project needs memory. A
regression ratchet is the rule that a known accepted baseline cannot degrade
without an explicit reason. It should compare stable, committed fixture outputs
and local dirty benchmark summaries when available.

This task turns quality from a point-in-time check into a trend-aware gate.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Defines which regressions block and which deltas require human classification |
| Task Worker | Builds baseline files, diff script and red tests for regression detection |
| Reviewer | Checks determinism, path privacy and intentional-baseline-update policy |
| Approval | Runs ratchet tests, parser tests, benchmark smoke, lint, type checks and secret scan |

## Scope

- Define a committed baseline format for parser fragility fixtures.
- Capture stable counts and quality signals:
  - metadata expected hits;
  - negative expectation passes;
  - adversarial risk emissions;
  - invariant pass counts;
  - review packet reason counts;
  - benchmark schema version.
- Build a ratchet script that:
  - compares current output to baseline;
  - fails on strict regressions;
  - reports neutral deltas;
  - reports improvements;
  - allows intentional baseline updates only with a reason string.
- Keep private local dirty PDF paths out of committed artifacts.
- Treat missing optional real dirty corpus as skipped, not passed.

## Out Of Scope

- Full CI wiring.
- Product outcome metrics.
- Runtime app gates.
- Benchmark UI dashboards.
- Hermes, Tri-Memory or agent infrastructure repair.

## Proposed Files

- Create: `scripts/quality/parser_regression_ratchet.py`
- Create: `examples/parser_fragility/baselines/parser-fragility-baseline.v1.json`
- Create: `tests/smoke/test_parser_regression_ratchet.py`
- Modify: `docs/07-qa/PARSER_FIXTURE_FACTORY.md`
- Modify: `tasks/TASK-036-parser-regression-ratchet.md`

## Acceptance

- Ratchet test fails when a required signal drops below baseline.
- Ratchet test passes when output matches baseline.
- Ratchet report distinguishes regression, neutral delta and improvement.
- Baseline update command requires a non-empty reason.
- Committed baseline contains no absolute local paths.
- Optional dirty-corpus comparison is marked as skipped when `.run` inputs are
  absent.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_regression_ratchet.py -q
uv run --cache-dir .uv-cache pytest packages\parsers\tests tests\smoke\test_parser_fragility_fixtures.py -q
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [x] Add red tests for baseline regression detection.
- [x] Add red tests for baseline update reason enforcement.
- [x] Add the baseline JSON format.
- [x] Implement the ratchet comparison script.
- [x] Add path privacy checks.
- [x] Run the verification target.
- [x] Record execution evidence in this task file.

## Execution Evidence

TDD red:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_regression_ratchet.py -q
```

Result: `5 failed`; expected `FileNotFoundError` for missing
`scripts\quality\parser_regression_ratchet.py`.

TDD red after adding the script:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_regression_ratchet.py -q
```

Result: `2 failed`; expected `FileNotFoundError` for missing
`examples\parser_fragility\baselines\parser-fragility-baseline.v1.json`.

TDD green:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_regression_ratchet.py -q
```

Result: `5 passed`.

Review-fix TDD red:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_regression_ratchet.py -q
```

Result: `6 failed, 4 passed`; expected failures covered directional signal
policy, top-level identity comparison, actual invariant pass counting and
unknown negative-expectation scenarios.

Review-fix intermediate red:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_regression_ratchet.py -q
```

Result: `1 failed, 9 passed`; expected baseline mismatch after replacing
manifest-count invariants with concrete invariant pass counts.

Review-fix TDD green:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_regression_ratchet.py -q
```

Result: `11 passed`.

Optional dirty corpus skip check:

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_regression_ratchet.py --dirty-corpus-dir .run\industrial-real-missing-for-ratchet-test
```

Result: exit `0`; report status `pass` with
`dirty_corpus_optional.status = "skipped"` and no regressions.

Verification target:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_regression_ratchet.py -q
```

Result: `11 passed`.

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests tests\smoke\test_parser_fragility_fixtures.py -q
```

Result: `134 passed`.

```powershell
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
```

Result: `All checks passed!`.

```powershell
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
```

Result: `Success: no issues found in 16 source files`.

```powershell
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Result: exit `0`.
