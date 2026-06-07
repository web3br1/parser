# TASK-037 - Parser Quality Gate On Top

Status: completed

## Goal

Create a top-level Parser quality gate that orchestrates lower test layers
without replacing them.

## Background

The project should not jump directly from individual tests to an executive
score. The top gate must sit above fragility catalog validation, fixture
validation, negative/adversarial tests, invariants, regression ratchet and
dirty benchmark diagnostics. It should answer whether the Parser is eligible
for more capability work or release hardening.

This task creates the director-level gate for Parser quality.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Owns layer order and blocks the gate from hiding failed lower layers |
| Task Worker | Builds the gate runner, report shape and smoke tests |
| Reviewer | Checks that the gate is transparent, deterministic and actionable |
| Approval | Runs full Parser quality verification and secret scan |

## Scope

- Define quality layers:
  - `catalog`;
  - `fixtures`;
  - `negative_adversarial`;
  - `invariants`;
  - `regression_ratchet`;
  - `dirty_benchmark_optional`;
  - `lint_type_secret`.
- Build a gate runner that reports:
  - layer status;
  - command run;
  - pass/fail/skip result;
  - failure summary;
  - next action category.
- Ensure the top gate fails if any required lower layer fails.
- Ensure optional local dirty-corpus checks are reported as skipped when inputs
  are missing.
- Create a runbook for when to use the gate:
  - before new parser capability work;
  - before release readiness claims;
  - after benchmark baseline updates.

## Out Of Scope

- New parser extraction features.
- CI provider configuration.
- Runtime app gates.
- Product analytics dashboard.
- Hermes, Tri-Memory or agent infrastructure repair.

## Proposed Files

- Create: `scripts/quality/parser_quality_gate.py`
- Create: `tests/smoke/test_parser_quality_gate.py`
- Create: `docs/07-qa/PARSER_QUALITY_GATE_RUNBOOK.md`
- Modify: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- Modify: `tasks/TASK-037-parser-quality-gate-on-top.md`

## Acceptance

- Gate runner exposes a deterministic JSON report.
- Required lower-layer failure makes the top gate fail.
- Optional dirty-corpus absence is reported as skipped with a reason.
- Gate output includes next action categories:
  - `write_red_test`;
  - `fix_parser`;
  - `update_baseline_with_reason`;
  - `inspect_dirty_corpus`;
  - `ready_for_next_slice`.
- Runbook explains how Orchestrator, Task Worker, Reviewer and Approval use the
  gate.
- No lower-layer failure is hidden behind an aggregate score.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_quality_gate.py -q
uv run --cache-dir .uv-cache pytest packages\parsers\tests tests\smoke -q
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [x] Add red tests for required layer failure propagation.
- [x] Add red tests for optional dirty-corpus skip reporting.
- [x] Add red tests for next action categories.
- [x] Implement the quality gate runner.
- [x] Add the Parser quality gate runbook.
- [x] Update dirty benchmark docs to reference the gate layer.
- [x] Run the verification target.
- [x] Record execution evidence in this task file.

## Execution Evidence

TDD red:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_quality_gate.py -q
```

Result: `5 failed`; expected `FileNotFoundError` for missing
`scripts\quality\parser_quality_gate.py`.

TDD green:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_quality_gate.py -q
```

Result: `5 passed`.

Integration gate run:

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_quality_gate.py --report .run\parser-quality-gate-latest.json
```

Result: exit `0`; report status `pass`, required failed layers `[]`, and
`dirty_benchmark_optional.result = "pass"` because `.run\industrial-real`
was available locally.

Verification target:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_quality_gate.py -q
```

Result: `5 passed`.

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests tests\smoke -q
```

Result: `231 passed`.

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
