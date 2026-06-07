# TASK-027 - Header/Footer Resolver And Section Tree Hardening

Status: completed

## Goal

Turn the page-level diagnostics from TASK-026 into a reliable document structure
layer for industrial/QMS PDFs: recurring header/footer evidence, section
headings, subsection paths and structure risk signals.

## Background

TASK-024 proved the real dirty-document benchmark is repeatable. TASK-025
closed the first deterministic document-code misses. TASK-026 added page
profiles and parse diagnostics. The next product gap is structural: the parser
can expose pages and metadata, but downstream chunking still has weak knowledge
of which text belongs to a QMS section, which text is boilerplate and which
pages have ambiguous layout.

This task is Parser-only. It must not introduce Hermes, Tri-Memory, agent
runtime dependencies or memory workflows.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Owns scope, ensures Parser-only boundaries and dispatches one worker task at a time |
| Task Worker | Adds red tests first, implements the section resolver and updates benchmark docs |
| Reviewer | Checks false-positive risk, metadata compatibility and `context_bundle.v1` preservation |
| Approval | Runs parser tests, benchmark smoke, lint/type checks and secret scan |

## Scope

- Detect repeated page headers and footers across PDF pages.
- Mark boilerplate spans without deleting source text from parser output.
- Recognize numbered industrial headings such as `1`, `1.1`, `2.3.4`.
- Recognize common QMS headings such as `Objetivo`, `Aplicacao`,
  `Responsabilidades`, `Procedimento`, `Registros`, `Anexos` and equivalents
  with common accent/uppercase variations.
- Build stable `section_path` values for structural hints.
- Preserve page profile metadata added by TASK-026.
- Add section diagnostic summaries to the dirty-document benchmark.
- Keep ambiguous structure visible through risk codes instead of forcing unsafe
  section assignments.

## Out Of Scope

- OCR.
- Visual model calls.
- Table extraction into rows/cells.
- Figure interpretation.
- Semantic requirement/responsibility extraction.
- Hierarchical chunking changes beyond exposing structure metadata.
- Human review UI changes.
- `context_bundle.v2` or top-level bundle schema changes.
- Hermes, Tri-Memory or agent runtime repair.

## Proposed Files

- Create: `packages/parsers/src/parsers/industrial_sections.py`
- Create: `packages/parsers/tests/test_industrial_sections.py`
- Modify: `packages/parsers/src/parsers/industrial_structure.py`
- Modify: `packages/parsers/tests/test_industrial_structure.py`
- Modify: `packages/parsers/src/parsers/pdf.py`
- Modify: `packages/parsers/tests/test_pdf.py`
- Modify: `scripts/industrial/benchmark_dirty_documents.py`
- Modify: `tests/smoke/test_industrial_dirty_benchmark.py`
- Modify: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- Modify: `tasks/TASK-027-header-footer-section-tree.md`

## Acceptance

- Repeated headers are detected and reported separately from body content.
- Repeated footers and page-number lines are detected and reported separately
  from body content.
- Parser output text remains available; resolver metadata must not silently
  delete source text.
- Numbered headings produce stable `section_path` values.
- Common QMS headings produce stable `section_path` values.
- Ambiguous headings produce risk codes instead of unsafe hierarchy.
- Existing TASK-025 metadata behavior is not regressed.
- Existing TASK-026 page profile behavior is not regressed.
- Benchmark report includes section diagnostics per document.
- No Hermes, Tri-Memory or memory workflow dependency is introduced.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_sections.py packages\parsers\tests\test_industrial_structure.py -q
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_pdf.py packages\parsers\tests\test_page_profile.py packages\parsers\tests\test_industrial_metadata.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [ ] Add red tests for recurring header/footer detection.
- [ ] Add red tests for numbered section paths.
- [ ] Add red tests for common QMS headings.
- [ ] Add red tests for ambiguous heading risk codes.
- [ ] Implement the section resolver with conservative defaults.
- [ ] Wire section diagnostics into PDF metadata without changing parsed text.
- [ ] Add benchmark section diagnostics.
- [ ] Update benchmark documentation.
- [ ] Run the verification target.
- [ ] Record execution evidence in this task file.

## Execution Evidence

Completed on 2026-06-06.

- Added `industrial_sections` resolver with recurring header/footer evidence,
  section spans, stable paths and structure risk codes.
- Wired PDF metadata and dirty benchmark section diagnostics without deleting
  parser text.
- Verification included parser section/PDF/page-profile tests, dirty benchmark
  smoke, real benchmark run, ruff, mypy and secret scan.
