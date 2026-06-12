# Parser Ground Truth Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Parser ground truth evaluator and wire it into the Parser quality gate.

**Architecture:** Add a small committed parser ground truth corpus and a standalone `scripts/quality/parser_ground_truth_eval.py` CLI. The evaluator runs the existing dirty benchmark over that corpus, converts parser outputs into canonical items, compares them with manifest expectations, and reports precision/recall gates without adding parser capability.

**Tech Stack:** Python 3.13 via `uv`, pytest, existing parser modules, existing industrial benchmark script, JSON manifests.

---

## Execution Model

Use SDD with four roles:

1. **Orchestrator** owns scope, sequencing and cross-task integration.
2. **Task Worker** uses TDD and edits only the assigned files.
3. **Spec Reviewer** checks this plan and `TASK-038` acceptance.
4. **Code Reviewer** checks determinism, privacy and maintainability.

Do not introduce OCR, vision, LLM adjudication, Hermes or Tri-Memory.

## File Map

Create:

- `examples/parser_ground_truth/manifest.json`: committed expected parser truth items.
- `examples/parser_ground_truth/POP-QA-014_Rev04_vigent.txt`: positive controlled-document fixture.
- `examples/parser_ground_truth/toc_noise.txt`: negative TOC/appendix fixture.
- `scripts/quality/parser_ground_truth_eval.py`: evaluator CLI and pure comparison functions.
- `tests/smoke/test_parser_ground_truth_eval.py`: smoke/unit tests for evaluator.
- `docs/07-qa/PARSER_GROUND_TRUTH_EVALUATION.md`: runbook.

Modify:

- `scripts/quality/parser_quality_gate.py`: add required `ground_truth_eval` layer.
- `tests/smoke/test_parser_quality_gate.py`: assert new layer order and failure action.
- `tasks/TASK-038-parser-ground-truth-evaluation.md`: execution evidence.

## Task 1: Evaluator Red Tests And Manifest Shape

**Files:**
- Create: `tests/smoke/test_parser_ground_truth_eval.py`
- Create: `examples/parser_ground_truth/manifest.json`
- Create: `examples/parser_ground_truth/POP-QA-014_Rev04_vigent.txt`
- Create: `examples/parser_ground_truth/toc_noise.txt`

- [ ] **Step 1: Add the committed mini-corpus**

Create `examples/parser_ground_truth/POP-QA-014_Rev04_vigent.txt` with a controlled-document header, numbered section, requirement, form reference, table-like row and figure reference.

Create `examples/parser_ground_truth/toc_noise.txt` with a table of contents that contains normative words and nested POP references that must remain negative expectations.

- [ ] **Step 2: Add manifest expectations**

Create `examples/parser_ground_truth/manifest.json` with:

```json
{
  "schema_version": "parser_ground_truth_manifest.v1",
  "documents": [
    {
      "filename": "POP-QA-014_Rev04_vigent.txt",
      "expected_code": "POP-QA-014",
      "expected_revision": "04",
      "expected_processing_mode": "single_parser",
      "expected": [
        {"kind": "metadata", "type": "document_code", "canonical": "POP-QA-014"},
        {"kind": "metadata", "type": "revision", "canonical": "04"},
        {"kind": "section", "type": "section_path", "canonical": "1"},
        {"kind": "semantic", "type": "requirement", "canonical": "Toda nao conformidade deve ser registrada."},
        {"kind": "semantic", "type": "form_reference", "canonical": "FOR-QA-002"},
        {"kind": "table_figure", "type": "text_table", "canonical": "table_present"},
        {"kind": "table_figure", "type": "figure_reference", "canonical": "Figura 1"},
        {"kind": "review_packet", "type": "missing_metadata", "canonical": "absent"}
      ]
    },
    {
      "filename": "toc_noise.txt",
      "expected": [
        {"kind": "metadata", "type": "document_code", "canonical": "POP 101", "negative": true},
        {"kind": "semantic", "type": "requirement", "canonical": "5.1 Deve registrar incidentes", "negative": true}
      ]
    }
  ]
}
```

- [ ] **Step 3: Write failing evaluator tests**

Create tests that import `scripts/quality/parser_ground_truth_eval.py`, call pure functions with small benchmark-like payloads, and assert:

- matching predictions produce precision/recall `1.0`;
- missing expected positive item fails recall;
- predicted negative item increments `critical_false_positives`;
- CLI writes deterministic JSON without absolute temp paths.

- [ ] **Step 4: Run red tests**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_ground_truth_eval.py -q
```

Expected: FAIL because `parser_ground_truth_eval.py` does not exist.

## Task 2: Implement Ground Truth Evaluator

**Files:**
- Create: `scripts/quality/parser_ground_truth_eval.py`
- Modify: `tests/smoke/test_parser_ground_truth_eval.py`

- [ ] **Step 1: Implement manifest loading and item normalization**

Add schema constants, `load_manifest`, canonicalization and `_item_key` helpers. Follow `scripts/pilot/semantic_metrics.py` style for normalized comparison.

- [ ] **Step 2: Implement benchmark prediction extraction**

Convert benchmark document rows into parser prediction items:

- metadata document code and revision;
- section paths from `section_diagnostics.section_spans`;
- semantic candidates by `kind` and normalized text/content;
- table/figure candidates by `kind` and label/table presence;
- review packet reason codes from `review_packet_summary.reason_code_counts`.

- [ ] **Step 3: Implement metrics and gate**

Compute precision, recall, f1, missing positives, false positives and critical false positives. Required gates:

- precision `>= 0.85`;
- recall `>= 0.75`;
- critical false positives `= 0`.

- [ ] **Step 4: Implement CLI**

Default command:

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_ground_truth_eval.py
```

The CLI should default to `examples/parser_ground_truth/manifest.json`, run `scripts.industrial.benchmark_dirty_documents.build_report` over `examples/parser_ground_truth`, print deterministic JSON and return `0` on pass, `1` on evaluated gate failure, `2` on invalid input.

- [ ] **Step 5: Run green tests**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_ground_truth_eval.py -q
```

Expected: PASS.

## Task 3: Quality Gate Integration

**Files:**
- Modify: `scripts/quality/parser_quality_gate.py`
- Modify: `tests/smoke/test_parser_quality_gate.py`

- [ ] **Step 1: Add red gate tests**

Update `test_gate_report_has_ordered_layers_and_skips_missing_dirty_corpus` to expect `ground_truth_eval` between `invariants` and `regression_ratchet`.

Add a test where `FakeRunner` fails on `parser_ground_truth_eval.py` and assert:

- top-level status is `fail`;
- `required_failed_layers == ["ground_truth_eval"]`;
- failed layer `next_action == "fix_parser"`.

- [ ] **Step 2: Run red gate tests**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_quality_gate.py -q
```

Expected: FAIL because the layer is not implemented yet.

- [ ] **Step 3: Implement gate layer**

Add required layer:

```python
LayerSpec(
    name="ground_truth_eval",
    required=True,
    commands=(_uv("python", "scripts\\quality\\parser_ground_truth_eval.py"),),
    failure_next_action="fix_parser",
)
```

Place it after `invariants` and before `regression_ratchet`.

- [ ] **Step 4: Run green gate tests**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_quality_gate.py -q
```

Expected: PASS.

## Task 4: Documentation And Evidence

**Files:**
- Create: `docs/07-qa/PARSER_GROUND_TRUTH_EVALUATION.md`
- Modify: `docs/07-qa/PARSER_QUALITY_GATE_RUNBOOK.md`
- Modify: `tasks/TASK-038-parser-ground-truth-evaluation.md`

- [ ] **Step 1: Write runbook**

Document purpose, command, manifest shape, gates, extension rules and privacy guardrails.

- [ ] **Step 2: Update quality gate runbook**

Add `ground_truth_eval` to the layer table and describe `fix_parser` as the next action for ground truth failures.

- [ ] **Step 3: Record execution evidence**

Update `TASK-038` with completed checklist items and verification command results.

## Final Verification

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_ground_truth_eval.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_quality_gate.py -q
uv run --cache-dir .uv-cache python scripts\quality\parser_ground_truth_eval.py
uv run --cache-dir .uv-cache ruff check scripts\quality tests\smoke\test_parser_ground_truth_eval.py tests\smoke\test_parser_quality_gate.py
uv run --cache-dir .uv-cache mypy --ignore-missing-imports scripts\quality\parser_ground_truth_eval.py scripts\quality\parser_quality_gate.py
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected:

- evaluator tests pass;
- quality gate tests pass;
- evaluator CLI exits `0`;
- ruff passes;
- mypy passes;
- secret scan exits `0`.
