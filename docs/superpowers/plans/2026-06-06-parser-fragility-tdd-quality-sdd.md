# Parser Fragility TDD Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise Parser quality maturity by using TDD to expose, fix and prevent known fragility classes before adding more extraction capability.

**Architecture:** Build a layered quality system from the bottom up: fragility catalog, deterministic fixtures, negative/adversarial tests, invariants, regression ratchet and a top-level quality gate. Benchmarks become the visible report layer, not the foundation.

**Tech Stack:** Python 3.12, pytest, existing `packages/parsers` modules, committed fixture files under `examples`, smoke tests under `tests/smoke`, quality scripts under `scripts/quality`.

---

## Scope Boundary

This plan is Parser quality infrastructure work. It does not add new product
extraction capability except where a red test exposes an unsafe existing
behavior and a minimal parser correction is required.

In scope:

- Parser quality docs under `docs/07-qa`.
- Task files `TASK-032` through `TASK-037`.
- Parser fragility fixtures under `examples/parser_fragility`.
- Parser tests under `packages/parsers/tests`.
- Smoke tests under `tests/smoke`.
- Quality scripts under `scripts/quality`.
- Existing dirty benchmark integration as a diagnostic layer.

Out of scope:

- Hermes and Tri-Memory.
- Agent memory workflows.
- Human review UI.
- Runtime app integration.
- CI provider configuration.
- OCR, vision or LLM adjudication.
- New `context_bundle.v2` schema work.

## Execution Model

Use SDD with four explicit roles:

| Role | Responsibility |
|------|----------------|
| Orchestrator | Owns sequencing, scope and quality philosophy; rejects vague metrics and overbroad fixes |
| Task Worker | Executes one task at a time using red-green-refactor; every behavior change starts with a failing test |
| Reviewer | Reviews spec compliance first, then code quality and false-positive risk |
| Approval | Runs verification gates and blocks completion when evidence is incomplete |

Do not dispatch multiple implementation workers against the same parser modules
at the same time. TASK-032 and TASK-033 are documentation/fixture foundations.
TASK-034 through TASK-037 should run sequentially because each consumes the
previous layer.

## Quality Ladder

The work intentionally separates layers:

1. **Fragility Catalog:** names the ways the parser can fail or lie.
2. **Fixture Factory:** creates minimal reproducible documents for those
   fragilities.
3. **Negative/Adversarial Tests:** prove unsafe claims are rejected.
4. **Invariants:** enforce parser laws independent from individual examples.
5. **Regression Ratchet:** prevents accepted quality from silently drifting.
6. **Quality Gate:** reports whether the Parser is ready for more capability
   work or release hardening.

Benchmarks remain valuable, but they sit above these layers as reporting and
triage evidence.

## Task Sequence

### TASK-032: Parser Fragility Catalog

**Task file:** `tasks/TASK-032-parser-fragility-catalog.md`

**Purpose:** Establish the catalog of named parser fragilities and convert
quality concerns into red-test hypotheses.

**Primary files:**

- `docs/07-qa/PARSER_FRAGILITY_CATALOG.md`
- `tests/smoke/test_parser_fragility_catalog.py`
- `tasks/TASK-032-parser-fragility-catalog.md`

**Gate:** PASS only when every catalog entry has an ID, severity, affected
layer, failure hypothesis, red-test target and expected benchmark signal.

### TASK-033: TDD Fixture Factory

**Task file:** `tasks/TASK-033-tdd-fixture-factory.md`

**Purpose:** Create committed, deterministic fixtures that reproduce cataloged
fragilities without relying on private dirty PDFs.

**Primary files:**

- `examples/parser_fragility/manifest.json`
- `examples/parser_fragility/*.txt`
- `docs/07-qa/PARSER_FIXTURE_FACTORY.md`
- `tests/smoke/test_parser_fragility_fixtures.py`

**Gate:** PASS only when every fixture links to a fragility ID and carries
positive, negative or invariant expectations.

### TASK-034: Negative And Adversarial Parser Tests

**Task file:** `tasks/TASK-034-negative-adversarial-parser-tests.md`

**Purpose:** Use fixtures to write red tests that expose unsafe parser
promotions and overclaims.

**Primary files:**

- `packages/parsers/tests/test_industrial_negative_adversarial.py`
- `packages/parsers/src/parsers/industrial_metadata.py`
- `packages/parsers/src/parsers/industrial_sections.py`
- `packages/parsers/src/parsers/industrial_semantics.py`
- `packages/parsers/src/parsers/industrial_tables.py`
- `packages/parsers/src/parsers/industrial_review.py`

**Gate:** PASS only when metadata, semantic, visual, structure and review-noise
overclaims are covered by negative/adversarial tests and minimal fixes.

### TASK-035: Parser Invariant Test Harness

**Task file:** `tasks/TASK-035-parser-invariant-test-harness.md`

**Purpose:** Enforce parser laws that must hold across all fixtures and output
objects.

**Primary files:**

- `packages/parsers/tests/test_industrial_invariants.py`
- `packages/parsers/tests/industrial_invariant_helpers.py`
- `packages/parsers/tests/test_industrial_negative_adversarial.py`

**Gate:** PASS only when evidence, page spans, risk codes, chunks and review
packets are checked by reusable invariant tests.

### TASK-036: Parser Regression Ratchet

**Task file:** `tasks/TASK-036-parser-regression-ratchet.md`

**Purpose:** Preserve accepted quality baselines and fail silent regressions.

**Primary files:**

- `scripts/quality/parser_regression_ratchet.py`
- `examples/parser_fragility/baselines/parser-fragility-baseline.v1.json`
- `tests/smoke/test_parser_regression_ratchet.py`

**Gate:** PASS only when strict regressions fail, neutral deltas are reported,
improvements are visible and baseline updates require a reason.

### TASK-037: Parser Quality Gate On Top

**Task file:** `tasks/TASK-037-parser-quality-gate-on-top.md`

**Purpose:** Create the director-level gate that orchestrates lower layers
without hiding failures behind a single score.

**Primary files:**

- `scripts/quality/parser_quality_gate.py`
- `tests/smoke/test_parser_quality_gate.py`
- `docs/07-qa/PARSER_QUALITY_GATE_RUNBOOK.md`
- `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`

**Gate:** PASS only when required layer failures fail the top gate, optional
dirty-corpus absence is marked skipped and next action categories are
actionable.

## Global Verification

Run the task-specific verification target from each task file. Before declaring
the quality program complete, run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_catalog.py tests\smoke\test_parser_fragility_fixtures.py -q
uv run --cache-dir .uv-cache pytest packages\parsers\tests -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_regression_ratchet.py tests\smoke\test_parser_quality_gate.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py tests\api\test_context_bundle.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected final evidence:

- Fragility catalog validates.
- Fixture manifest validates.
- Negative/adversarial parser tests pass.
- Invariant harness catches malformed objects and accepts valid outputs.
- Regression ratchet detects simulated regressions.
- Quality gate reports lower-layer failures transparently.
- Dirty benchmark remains diagnostic and does not hide known gaps.
- No Hermes or Tri-Memory dependency is introduced into Parser.

## Review Rules

Reviewer must reject a slice if it:

- adds parser behavior without a red test first;
- turns a benchmark count into a success claim without a test underneath;
- hides lower-layer failures behind an aggregate score;
- promotes uncertain evidence to trusted truth;
- weakens context bundle compatibility;
- commits private dirty PDFs or absolute local paths;
- introduces Hermes, Tri-Memory or agent runtime dependencies.

