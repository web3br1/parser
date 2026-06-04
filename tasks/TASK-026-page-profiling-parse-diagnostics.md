# TASK-026 - Page Profiling And Parse Diagnostics

Status: implemented; benchmark executed locally

## Goal

Add a page intelligence pass for PDFs so the industrial parser can diagnose each
page before later semantic extraction, chunking or review decisions.

## Background

TASK-024 proved that the benchmark can process dirty industrial documents, and
TASK-025 improved deterministic metadata extraction for real controlled-document
codes. The next parser gap is operational visibility: today the PDF parser
returns text pages and high-level metrics, but it does not expose per-page
signals such as image-only pages, likely OCR need, table candidates,
header/footer presence, rotation or layout risk.

This task implements the next roadmap slice from the pasted architecture:
`Page Profiling & Parse Diagnostics`.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Agent Orchestrator | Owns task sequence, context handoff, branch hygiene and blocker resolution |
| Agent Task | Implements one plan task at a time using tests first |
| Agent Reviewer | Reviews spec compliance first, then code quality, after each task |
| Agent Approval | Runs final acceptance gates and blocks completion on missing evidence |

## Scope

- Create a parser-level page profile model for PDF pages.
- Detect per-page:
  - text character count;
  - text/image presence flags;
  - line count;
  - block count;
  - embedded image count;
  - likely table candidate count;
  - likely OCR requirement;
  - OCR and table risk aliases;
  - text layer type;
  - layout complexity;
  - page rotation;
  - empty page flag;
  - header/footer presence;
  - risk codes.
- Attach page profiles and a compact diagnostic summary to `PDFParser` metadata.
- Extend the industrial dirty-document benchmark report with page diagnostics.
- Add tests for text pages, image-only pages, parser metadata and benchmark JSON.
- Document the diagnostics and out-of-scope limits.

## Out Of Scope

- OCR implementation.
- Vision model calls.
- Table extraction into rows/cells.
- Section tree rebuilding.
- Hierarchical chunking changes.
- Semantic unit extraction.
- Human review UI changes.
- `context_bundle.v2` or top-level bundle schema changes.

## Proposed Files

- Create: `packages/parsers/src/parsers/page_profile.py`
- Create: `packages/parsers/tests/test_page_profile.py`
- Modify: `packages/parsers/src/parsers/pdf.py`
- Modify: `packages/parsers/tests/test_pdf.py`
- Modify: `scripts/industrial/benchmark_dirty_documents.py`
- Modify: `tests/smoke/test_industrial_dirty_benchmark.py`
- Modify: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- Create: `docs/superpowers/plans/2026-06-03-page-profiling-parse-diagnostics-sdd.md`

## Acceptance

- `profile_pdf_pages()` returns one profile per PDF page under the parser page
  limit.
- Digital text pages are not marked as OCR required.
- Image-only pages with no text are marked as OCR required.
- Header/footer detection works on simple top/bottom PDF text fixtures.
- Table-like text lines increment table candidate counts.
- `PDFParser.extract()` preserves existing pages/text behavior and adds
  `metadata["page_profiles"]` plus `metadata["page_profile_summary"]`.
- The benchmark report includes page diagnostic summaries per document.
- Existing TASK-025 metadata benchmark behavior is not regressed.
- Documentation explains that diagnostics route later strategies but do not
  perform OCR or visual understanding.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_page_profile.py packages\parsers\tests\test_pdf.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Evidence

Focused parser tests:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_page_profile.py packages\parsers\tests\test_pdf.py -q
```

Observed: `9 passed`.

Benchmark and parser regression tests:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py packages\parsers\tests\test_pdf.py packages\parsers\tests\test_page_profile.py -q
```

Observed: `15 passed`.

Type and lint checks:

```powershell
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
```

Observed:

- `ruff check packages\parsers scripts tests` passed;
- `mypy --ignore-missing-imports -p parsers` passed with no issues in 12 parser
  source files.
- `python scripts\ci\secret_scan.py` completed with exit code 0.

Real benchmark:

```powershell
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
```

Observed diagnostic summary:

- documents: 5;
- parsed: 5;
- failed: 0;
- split processed: 1;
- text pages: 56;
- image pages: 56;
- OCR-required pages: 0;
- OCR-risk pages: 0;
- image-only pages: 0;
- table-candidate pages: 0;
- table-risk pages: 0;
- header-detected pages: 56;
- footer-detected pages: 54;
- metadata gaps: `missing_document_code: 1`, `missing_revision: 1`.
- known findings: 0.

Notes:

- The large PMPR stress PDF keeps the default page profile summary because it
  uses split-page fallback.
- `page_profiles` now exposes stable boolean aliases: `has_text`,
  `has_images`, `ocr_risk` and `table_risk`.
- `page_profile_summary` preserves its original keys and adds stable routing
  aliases such as `text_pages`, `image_pages`, `ocr_risk_pages`,
  `table_risk_pages`, `layout_complexity` and `risk_codes`.
- The `uv` commands may emit local `SSL_CERT_DIR` warnings; they did not affect
  exit status.

## Follow-Up Tasks

- TASK-027: Header/footer resolver and section tree hardening.
- TASK-028: Hierarchical industrial chunking with section paths.
- TASK-029: Technical semantic unit extraction with evidence.
- TASK-030: Table and figure understanding.
- TASK-031: Human review packets for low-confidence industrial diagnostics.
