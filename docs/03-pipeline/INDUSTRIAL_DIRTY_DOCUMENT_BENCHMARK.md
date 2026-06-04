# Industrial Dirty Document Benchmark

Status: active local benchmark
Date: 2026-06-03

## Purpose

This benchmark compares the first industrial/QMS parser slice against real
technical documents with noisy layouts. It is local-only: it does not require
API, Supabase, review publication or `context_bundle.v1` export.

The benchmark measures parser behavior before OCR and before layout-aware visual
extraction. It should expose gaps clearly instead of hiding failures.

## Corpus

Real PDFs are downloaded into `.run/industrial-real`. They are not committed.

| File | Purpose |
|------|---------|
| `pop-o-snvs-010-rev4.pdf` | Clean official POP baseline with 14 pages |
| `dirty/bluesun-blu002-kit-fotovoltaico.pdf` | Industrial POP with diagrams, checklists and annexes |
| `dirty/cispar-pop-005-inspecao-concreto.pdf` | Dense technical inspection form |
| `dirty/hospitalregional-higienizacao-maos-figuras.pdf` | Long healthcare protocol with many figures |
| `dirty/ponte-pop-pmpr-fotos.pdf` | Large stress case processed with two page-range workers |

Source URLs are recorded in
`tasks/TASK-024-industrial-dirty-document-benchmark.md`.

## Command

```powershell
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
```

The report path is intentionally under `.run` so it can be regenerated without
committing private absolute paths or third-party PDF binaries.

## Metrics

Each document row records:

- stable document id;
- relative path;
- file size;
- MIME type and extension;
- page count;
- sheet count;
- embedded image count for PDFs;
- parser error;
- elapsed parse time in milliseconds;
- extracted character count;
- quality-gate result;
- deterministic industrial metadata candidate;
- metadata gap codes;
- structure hint count;
- page profile diagnostic summary;
- known findings against the expected dirty-corpus baseline.

## Page Profile Diagnostics

Each PDF parsed through the normal `PDFParser` path emits a
`page_profile_summary` object in the benchmark report. The summary is a routing
signal for later extraction strategy decisions, not an OCR or vision result.

Fields:

- `page_count`: number of profiled pages.
- `text_pages`: number of pages with extracted text.
- `image_pages`: number of pages with embedded images.
- `ocr_required_pages`: pages with embedded images and no extracted text.
- `ocr_risk_pages`: alias-style routing list for pages that require OCR.
- `empty_pages`: pages with no extracted text and no embedded images.
- `image_only_pages`: pages classified as `scanned_image`.
- `table_candidate_pages`: pages with simple table-like text signals.
- `table_risk_pages`: alias-style routing list for pages with table risk.
- `header_detected_pages`: pages with text in the top 15% band.
- `footer_detected_pages`: pages with text in the bottom 15% band.
- `layout_complexity_counts`: counts for `low`, `medium` and `high`.
- `layout_complexity`: stable alias of `layout_complexity_counts`.
- `text_layer_type_counts`: counts for `digital_text`, `mixed`,
  `scanned_image` and `empty`.
- `risk_code_counts`: aggregate parse risk codes such as `ocr_required`,
  `table_candidates_present`, `rotated_page` and `high_layout_complexity`.
- `risk_codes`: stable alias of `risk_code_counts`.

The profiler deliberately does not extract table cells, interpret figures,
perform OCR or change chunk boundaries. Those behaviors remain follow-up tasks.

## TASK-024 Baseline Result

Run on 2026-06-03:

| File | Pages | Images | Chars | Parser result | Findings |
|------|-------|--------|-------|---------------|----------|
| `pop-o-snvs-010-rev4.pdf` | 14 | 14 | 25,679 | parsed | misses `POP-O-SNVS-010` |
| `dirty/bluesun-blu002-kit-fotovoltaico.pdf` | 13 | 23 | 14,932 | parsed | misses `BLU002` |
| `dirty/cispar-pop-005-inspecao-concreto.pdf` | 4 | 4 | 7,019 | parsed | misses `POP 005` |
| `dirty/hospitalregional-higienizacao-maos-figuras.pdf` | 25 | 83 | 39,134 | parsed | misses `PTC.DEPQI-SCIRAS.001` and revision |
| `dirty/ponte-pop-pmpr-fotos.pdf` | 374 | 306 | 500,000 | split-page fallback | two workers process page ranges `0-187` and `187-374` |

Summary:

- documents: 5;
- parsed: 5;
- failed: 0;
- split processed: 1;
- total pages: 430;
- total embedded images: 430;
- total extracted characters: 586,764;
- parser errors: none;
- metadata gaps: `missing_document_code: 5`, `missing_revision: 2`.

## Current Result After TASK-025

Run on 2026-06-03 after deterministic metadata pattern expansion:

| File | Code | Revision | Parser result | Current gap signal |
|------|------|----------|---------------|--------------------|
| `pop-o-snvs-010-rev4.pdf` | `POP-O-SNVS-010` | `04` | parsed | none |
| `dirty/bluesun-blu002-kit-fotovoltaico.pdf` | `BLU002` | `00` | parsed | none |
| `dirty/cispar-pop-005-inspecao-concreto.pdf` | `POP 005` | `00` | parsed | none |
| `dirty/hospitalregional-higienizacao-maos-figuras.pdf` | `PTC.DEPQI-SCIRAS.001` | `1.0.0` | parsed | none |
| `dirty/ponte-pop-pmpr-fotos.pdf` | missing | missing | split-page fallback | `missing_document_code`, `missing_revision` |

Summary:

- documents: 5;
- parsed: 5;
- failed: 0;
- split processed: 1;
- total pages: 430;
- total embedded images: 430;
- total extracted characters: 586,764;
- parser errors: none;
- metadata gaps: `missing_document_code: 1`, `missing_revision: 1`;
- expected-code findings: none.

## Current Result After TASK-026

Run after page profiling and parse diagnostics:

| File | Profiled pages | Text layer signal | Layout signal | OCR-required pages | Table-candidate pages |
|------|----------------|-------------------|---------------|--------------------|-----------------------|
| `pop-o-snvs-010-rev4.pdf` | 14 | `mixed: 14` | `high: 14` | 0 | 0 |
| `dirty/bluesun-blu002-kit-fotovoltaico.pdf` | 13 | `mixed: 13` | `high: 13` | 0 | 0 |
| `dirty/cispar-pop-005-inspecao-concreto.pdf` | 4 | `mixed: 4` | `high: 4` | 0 | 0 |
| `dirty/hospitalregional-higienizacao-maos-figuras.pdf` | 25 | `mixed: 25` | `high: 25` | 0 | 0 |
| `dirty/ponte-pop-pmpr-fotos.pdf` | 0 | split fallback default | split fallback default | 0 | 0 |

Summary:

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
- metadata gaps remain: `missing_document_code: 1`, `missing_revision: 1`;
- known findings: 0.

The four normally parsed PDFs are classified as `mixed` because they contain
both extracted text and embedded images. The large PMPR stress PDF keeps the
default diagnostic summary because it uses the split-page fallback, which
extracts text by page range without preserving one profile per page.

## Interpretation

The current parser can extract substantial text from real technical PDFs with
images and complex headers. The largest stress PDF exceeds the single-parser
page guard, so the benchmark falls back to two page-range workers and caps
combined text at the existing parser character limit.

TASK-025 resolved the first deterministic metadata gap: document-code recognition
now expands beyond the synthetic `POP-QA-014` style to cover:

- multi-segment codes such as `POP-O-SNVS-010`;
- compact codes such as `BLU002`;
- spaced codes such as `POP 005`;
- dotted protocol codes such as `PTC.DEPQI-SCIRAS.001`.

The remaining metadata gaps are intentionally conservative:

- the PMPR PDF is a book-like collection of many POP sections, so section codes
  such as `POP 101` are not promoted to file-level metadata;
- only explicit version labels such as `Versao n.`/`Versao no.` are treated as
  revision metadata; broader version/revision policy remains a future semantic
  validation topic.

OCR, image caption extraction and visual layout reasoning remain out of scope
for this benchmark.

## Verification

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_page_profile.py packages\parsers\tests\test_pdf.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check scripts tests
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```
