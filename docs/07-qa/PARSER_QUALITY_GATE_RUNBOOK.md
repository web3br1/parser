# Parser Quality Gate Runbook

Status: active

## Purpose

The Parser quality gate is the top-level readiness check for parser quality
work. It sits above the lower layers instead of replacing them. A failing lower
layer remains visible in the JSON report with its command, result, summary and
next action.

Use this gate:

- before new parser capability work;
- before release-readiness claims;
- after accepting a parser fragility baseline update;
- after changing parser diagnostics that affect dirty benchmark signals.

Do not use this gate as an executive score. The report has no score field by
design.

## Command

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_quality_gate.py
```

To write the deterministic JSON report:

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_quality_gate.py --report .run\parser-quality-gate-latest.json
```

The optional dirty-corpus layer uses `.run\industrial-real` by default. If that
directory is absent, the layer is reported as skipped with
`next_action = "inspect_dirty_corpus"` and the required gate can still pass.

## Layers

| Layer | Required | Purpose | Next action on failure |
|-------|----------|---------|------------------------|
| `catalog` | yes | Validates the fragility catalog shape and taxonomy | `write_red_test` |
| `fixtures` | yes | Validates deterministic parser fragility fixtures | `write_red_test` |
| `negative_adversarial` | yes | Proves unsafe parser promotions are rejected | `fix_parser` |
| `invariants` | yes | Enforces parser laws across outputs | `fix_parser` |
| `regression_ratchet` | yes | Compares current signals to the accepted baseline | `update_baseline_with_reason` |
| `dirty_benchmark_optional` | no | Runs the local dirty-corpus diagnostic when inputs exist | `inspect_dirty_corpus` |
| `lint_type_secret` | yes | Runs parser lint, type checks and secret scan | `fix_parser` |

## Role Usage

| Role | Gate responsibility |
|------|---------------------|
| Orchestrator | Reads the report top-down and refuses to hide failed required layers behind aggregate wording. |
| Task Worker | Starts from the failed layer command and writes a red test before changing parser behavior. |
| Reviewer | Checks whether the layer result and next action match the failure, especially ratchet baseline changes. |
| Approval | Runs the gate and the task-specific verification target before any readiness claim. |

## Interpreting Actions

- `write_red_test`: add or tighten the lower test layer before implementation.
- `fix_parser`: repair parser behavior or invariant support, then rerun the failed command.
- `update_baseline_with_reason`: either fix the regression or update the ratchet baseline with a non-empty reason after review.
- `inspect_dirty_corpus`: regenerate or provide `.run\industrial-real` if real-PDF diagnostics are needed.
- `ready_for_next_slice`: all required layers passed; optional local diagnostics may still be skipped.

## Guardrails

- Do not commit private PDFs, `.run` reports or absolute local paths.
- Do not introduce OCR, vision or LLM adjudication into this gate.
- Do not add Hermes, Tri-Memory or agent runtime dependencies.
- Do not weaken lower tests to make the top gate green.
