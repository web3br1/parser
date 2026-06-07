# TASK-030 - Table And Figure Understanding

Status: completed

## Goal

Add first-pass table and figure understanding for industrial PDFs using
parser-visible layout/text signals, without OCR or visual model calls.

## Background

TASK-026 exposes page diagnostics, TASK-027 should expose section paths, and
TASK-029 should extract deterministic semantic units from text. Dirty industrial
documents also carry important meaning in tables, checklists, annex lists and
figure references. This task adds a conservative parser layer for those signals
without claiming full visual understanding.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Keeps this as parser-level evidence extraction, not OCR or vision |
| Task Worker | Adds red tests for table candidates, checklist rows and figure references |
| Reviewer | Reviews unsafe table promotion, evidence quotes and benchmark deltas |
| Approval | Runs parser tests, benchmark and regression gates |

## Scope

- Detect simple text-table candidates from aligned delimiters, repeated spacing
  and column-like lines.
- Extract checklist-like rows with labels/status fields when present in text.
- Extract figure/image references from captions and nearby text such as
  `Figura 1`, `Imagem`, `Anexo`, `Fluxograma`.
- Link table/figure candidates to page number, section path and quote.
- Add risk codes when a page likely contains visual information not accessible
  through text extraction.
- Extend benchmark output with table/figure candidate summaries.

## Out Of Scope

- OCR.
- Computer vision or image captioning.
- Full table cell reconstruction for scanned images.
- Semantic extraction from image pixels.
- Spreadsheet parsing changes.
- Human review UI.
- `context_bundle.v2`.
- Hermes, Tri-Memory or agent runtime repair.

## Proposed Files

- Create: `packages/parsers/src/parsers/industrial_tables.py`
- Create: `packages/parsers/tests/test_industrial_tables.py`
- Modify: `packages/parsers/src/parsers/page_profile.py`
- Modify: `packages/parsers/tests/test_page_profile.py`
- Modify: `packages/parsers/src/parsers/industrial_structure.py`
- Modify: `packages/parsers/tests/test_industrial_structure.py`
- Modify: `scripts/industrial/benchmark_dirty_documents.py`
- Modify: `tests/smoke/test_industrial_dirty_benchmark.py`
- Modify: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- Modify: `tasks/TASK-030-table-and-figure-understanding.md`

## Acceptance

- Text-table candidates include page, section path, quote and confidence.
- Checklist candidates preserve row-like text and do not require perfect cell
  reconstruction.
- Figure references include caption/reference text and page evidence.
- Pages with images but no extractable captions keep explicit visual-risk codes.
- Benchmark report includes table/figure candidate counts and risk summaries.
- Existing page profile, metadata, section and chunking tests do not regress.
- No OCR, visual model or external service is introduced.
- No Hermes, Tri-Memory or memory workflow dependency is introduced.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_tables.py packages\parsers\tests\test_page_profile.py -q
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_structure.py packages\parsers\tests\test_industrial_semantics.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [ ] Add red tests for simple text-table candidate detection.
- [ ] Add red tests for checklist row candidates.
- [ ] Add red tests for figure/caption references.
- [ ] Add red tests for visual-risk pages without captions.
- [ ] Implement conservative table/figure helpers.
- [ ] Add benchmark summaries.
- [ ] Update benchmark documentation.
- [ ] Run the verification target.
- [ ] Record execution evidence in this task file.

## Execution Evidence

Completed on 2026-06-06.

- Added conservative text-table, checklist row, figure/reference and visual-risk
  candidates using text/page-profile signals only.
- Added `visual_content_without_caption` risk for image pages without strong
  extracted captions.
- Extended dirty benchmark with table/figure candidate and visual-risk
  summaries.
- Verification included table/page-profile tests, section/semantic regressions,
  dirty benchmark smoke, real benchmark run, ruff, mypy and secret scan.
