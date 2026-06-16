# TASK-038 - Parser Ground Truth Evaluation

Status: implemented

## Goal

Add a Parser-first ground truth evaluation harness that compares parser output
against committed expectations before new parser capability work proceeds.

## Background

TASK-032 through TASK-037 added the Parser quality ladder: fragility catalog,
fixtures, negative/adversarial tests, invariants, regression ratchet and a
top-level quality gate. Those layers prevent unsafe parser overclaims and
silent drift, but they mostly measure internal behavior.

The next quality gap is truth calibration. The dirty benchmark can report
counts for metadata, sections, semantic candidates, table/figure signals and
review packets, but it only compares a narrow set of metadata and processing
expectations. This task adds a committed, deterministic mini-corpus and an
evaluator that answers whether parser outputs match expected truth items.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Keeps this scoped to Parser quality evaluation and coordinates worker/reviewer roles. |
| Task Worker | Adds red tests first, implements the evaluator and gate integration. |
| Spec Reviewer | Confirms the implementation matches this task and does not add unrelated capability. |
| Code Reviewer | Checks determinism, privacy, maintainability and false-positive risk. |
| Approval | Runs focused tests, parser quality gate tests, lint/type checks and secret scan. |

## Scope

- Create a committed parser ground truth corpus under `examples/parser_ground_truth`.
- Create a deterministic CLI evaluator under `scripts/quality`.
- Compare parser benchmark outputs against expected canonical items.
- Report precision, recall, missing items, false positives and critical
  false positives.
- Treat negative expectations as critical when they are predicted by the parser.
- Add a required `ground_truth_eval` layer to the Parser quality gate.
- Document how to extend the manifest without committing private PDFs.

## Out Of Scope

- OCR.
- Vision or image captioning.
- LLM adjudication.
- Human review UI.
- `context_bundle.v2`.
- Dirty real PDF downloads in CI.
- Hermes, Tri-Memory or agent runtime dependencies.

## Proposed Files

- Create: `examples/parser_ground_truth/manifest.json`
- Create: `examples/parser_ground_truth/POP-QA-014_Rev04_vigent.txt`
- Create: `examples/parser_ground_truth/toc_noise.txt`
- Create: `scripts/quality/parser_ground_truth_eval.py`
- Create: `tests/smoke/test_parser_ground_truth_eval.py`
- Create: `docs/07-qa/PARSER_GROUND_TRUTH_EVALUATION.md`
- Create: `docs/superpowers/plans/2026-06-07-parser-ground-truth-evaluation-sdd.md`
- Modify: `scripts/quality/parser_quality_gate.py`
- Modify: `tests/smoke/test_parser_quality_gate.py`

## Acceptance

- Ground truth evaluator emits deterministic JSON with schema version
  `parser_ground_truth_eval.v1`.
- Manifest validates through evaluator tests.
- Positive expected items can match metadata, section paths, semantic
  candidates, table/figure candidates and review packet reasons.
- Negative expected items fail the gate when predicted.
- Missing positive items reduce recall and fail the gate.
- Unexpected positive predictions reduce precision and fail the gate when below
  threshold.
- CLI can write a report path and exits `0` on pass, `1` on evaluated failure
  and `2` on invalid input.
- Parser quality gate includes required `ground_truth_eval` before
  `regression_ratchet`.
- No absolute local paths, `.run` paths, private PDFs or generated timestamps are
  written to committed reports.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_ground_truth_eval.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_quality_gate.py -q
uv run --cache-dir .uv-cache python scripts\quality\parser_ground_truth_eval.py
uv run --cache-dir .uv-cache ruff check scripts\quality tests\smoke\test_parser_ground_truth_eval.py tests\smoke\test_parser_quality_gate.py
uv run --cache-dir .uv-cache mypy --ignore-missing-imports scripts\quality\parser_ground_truth_eval.py scripts\quality\parser_quality_gate.py
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [x] Add SDD plan for TASK-038.
- [x] Add red tests for matching ground truth items.
- [x] Add red tests for missing expected items.
- [x] Add red tests for negative expected false positives.
- [x] Add red tests for deterministic CLI report writing.
- [x] Implement parser ground truth evaluator.
- [x] Add committed mini-corpus and manifest.
- [x] Add required quality gate layer.
- [x] Add runbook documentation.
- [x] Run verification target.
- [x] Complete spec and code review loops.

## Execution Evidence

Implemented on 2026-06-07.

Red tests:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_ground_truth_eval.py -q
```

Observed first red result: `4 failed`, all due to missing
`scripts\quality\parser_ground_truth_eval.py`.

Current focused checks:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_ground_truth_eval.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_quality_gate.py -q
uv run --cache-dir .uv-cache python scripts\quality\parser_ground_truth_eval.py --repo-root .
```

Observed:

- ground truth evaluator tests: `6 passed`;
- parser quality gate tests: `6 passed`;
- parser ground truth CLI: exit `0`, status `pass`.
- `ruff check scripts\quality tests\smoke\test_parser_ground_truth_eval.py tests\smoke\test_parser_quality_gate.py`: `All checks passed!`;
- `mypy --ignore-missing-imports scripts\quality\parser_ground_truth_eval.py scripts\quality\parser_quality_gate.py`: `Success: no issues found in 2 source files`;
- `python scripts\ci\secret_scan.py`: exit `0`;
- top-level Parser quality gate: exit `0`, status `pass`, with
  `ground_truth_eval` required layer passing and `dirty_benchmark_optional`
  skipped because `.run\industrial-real` was absent.
- spec compliance review: approved with no P0/P1/P2 findings;
- code quality review: first pass found candidate-detail privacy and path-leak
  risks; after fixes, re-review approved with no remaining findings.

Local note:

- `tests\smoke\test_industrial_dirty_benchmark.py` skipped in this worktree
  because `fitz` is unavailable for that smoke module in the isolated venv.
