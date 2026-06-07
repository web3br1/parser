# Industrial Parser Next Five Slices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Advance the Parser product from page diagnostics to structured industrial document understanding across TASK-027 through TASK-031.

**Architecture:** Build five additive parser slices in order: section tree, section-aware chunking, deterministic semantic unit extraction, table/figure evidence and review packets. Each slice must preserve `context_bundle.v1`, avoid OCR/vision/LLM scope unless explicitly deferred, and keep Hermes/Tri-Memory out of the Parser product.

**Tech Stack:** Python 3.12, PyMuPDF (`fitz`), existing `parsers` package, pytest, ruff, mypy, dirty industrial benchmark harness.

---

## Scope Boundary

These tasks are Parser product work. They do not repair or depend on Hermes
agent infrastructure.

In scope:

- Parser modules under `packages/parsers`.
- Parser tests under `packages/parsers/tests`.
- Industrial benchmark script and smoke tests.
- Parser and pipeline documentation.
- Context bundle compatibility tests when review/readiness behavior changes.

Out of scope:

- Hermes profiles, Kanban workers and terminal backend repair.
- Tri-Memory integration into Parser.
- Memory candidate approval.
- Agent reviewer/memory-librarian workflow changes.
- Deployment, cron, hooks or automation.

## Execution Model

Use SDD with four explicit roles:

1. **Orchestrator** owns sequencing, scope and blocker resolution.
2. **Task Worker** implements one task at a time using tests first.
3. **Reviewer** reviews spec compliance first and code quality second.
4. **Approval** runs final acceptance gates and blocks completion on missing
   evidence.

Do not dispatch parallel workers against the same files. Do not start TASK-028
until TASK-027 is merged or explicitly accepted, because TASK-028 depends on
section path metadata. Continue this dependency chain through TASK-031.

## Task Sequence

### TASK-027: Header/Footer Resolver And Section Tree Hardening

**Task file:** `tasks/TASK-027-header-footer-section-tree.md`

**Purpose:** Convert page diagnostics into recurring boilerplate detection and
stable section paths.

**Primary files:**

- `packages/parsers/src/parsers/industrial_sections.py`
- `packages/parsers/tests/test_industrial_sections.py`
- `packages/parsers/src/parsers/industrial_structure.py`
- `scripts/industrial/benchmark_dirty_documents.py`

**Gate:** PASS only when headers/footers and QMS section paths are tested and
benchmark section diagnostics are documented.

### TASK-028: Hierarchical Industrial Chunking With Section Paths

**Task file:** `tasks/TASK-028-hierarchical-industrial-chunking.md`

**Purpose:** Make industrial chunks carry section paths, page spans and
structure risk metadata while preserving generic chunk behavior.

**Primary files:**

- `packages/parsers/src/parsers/chunker.py`
- `packages/parsers/tests/test_chunker.py`
- `scripts/industrial/benchmark_dirty_documents.py`

**Gate:** PASS only when generic chunking does not regress and industrial chunks
include deterministic section metadata.

### TASK-029: Technical Semantic Unit Extraction With Evidence

**Task file:** `tasks/TASK-029-technical-semantic-unit-extraction.md`

**Purpose:** Extract deterministic industrial requirements, responsibilities,
records/forms and procedure steps with evidence.

**Primary files:**

- `packages/parsers/src/parsers/industrial_semantics.py`
- `packages/parsers/tests/test_industrial_semantics.py`
- `scripts/industrial/benchmark_dirty_documents.py`

**Gate:** PASS only when candidates carry quotes, section paths and page spans
and no model calls are introduced.

### TASK-030: Table And Figure Understanding

**Task file:** `tasks/TASK-030-table-and-figure-understanding.md`

**Purpose:** Add conservative table/checklist/figure-reference candidates from
text and layout signals, without OCR or vision.

**Primary files:**

- `packages/parsers/src/parsers/industrial_tables.py`
- `packages/parsers/tests/test_industrial_tables.py`
- `packages/parsers/src/parsers/page_profile.py`
- `scripts/industrial/benchmark_dirty_documents.py`

**Gate:** PASS only when table/figure evidence is explicit and visual-risk
pages remain visible instead of being over-claimed.

### TASK-031: Human Review Packets For Industrial Diagnostics

**Task file:** `tasks/TASK-031-human-review-packets-industrial-diagnostics.md`

**Purpose:** Group low-confidence industrial diagnostics into review-ready
packets with evidence and suggested decisions.

**Primary files:**

- `packages/parsers/src/parsers/industrial_review.py`
- `packages/parsers/tests/test_industrial_review.py`
- `tests/api/test_context_bundle.py`
- `scripts/industrial/benchmark_dirty_documents.py`

**Gate:** PASS only when packets are deterministic, evidence-rich and compatible
with existing readiness blockers.

## Global Verification

Run the task-specific verification target from each task file. Before declaring
the five-slice roadmap complete, run:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py tests\api\test_context_bundle.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected final evidence:

- All parser tests pass.
- Industrial dirty benchmark parses the local corpus without hiding known gaps.
- Reports include section, chunk, semantic, table/figure and review packet
  summaries.
- No real PDF binaries or `.run` artifacts are committed.
- No Hermes or Tri-Memory dependency is introduced into Parser.

## Review Rules

Reviewer must reject a slice if it:

- introduces Hermes/Tri-Memory into Parser;
- mutates `context_bundle.v1` without a separate approved schema task;
- claims OCR or visual understanding without implementing it;
- hides dirty-document benchmark failures;
- removes source text to make diagnostics look cleaner;
- promotes low-confidence table-of-contents or reference text as file-level
  truth.

