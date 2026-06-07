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

## Parser Quality Gate Layer

The dirty benchmark is now orchestrated by the Parser quality gate as the
optional `dirty_benchmark_optional` layer. The benchmark remains diagnostic: it
does not replace the fragility catalog, fixtures, negative/adversarial tests,
invariants or regression ratchet.

Run the top gate before release-readiness claims or before adding more parser
capability:

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_quality_gate.py
```

If `.run\industrial-real` is absent, the quality gate reports this layer as
`skip` with `next_action = "inspect_dirty_corpus"` instead of pretending the
dirty corpus passed.

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
- section diagnostic summary;
- section-aware chunk diagnostic summary;
- semantic candidate diagnostic summary;
- table/figure candidate diagnostic summary;
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

## Section Tree Diagnostics

Each document row also records a `section_diagnostics` object. This is parser
metadata only: it does not delete extracted text and does not change
`context_bundle.v1`.

Fields:

- `boilerplate_spans`: repeated header/footer evidence with page, line index and
  quote.
- `section_spans`: numbered or QMS heading evidence with section path, page
  bounds and localized risk codes.
- `risk_codes`: document-level structure risks such as
  `ambiguous_section_heading` and `section_hierarchy_gap`.
- `summary.section_count`: number of detected section spans.
- `summary.section_path_count`: number of spans with stable section paths.
- `summary.boilerplate_counts`: header/footer evidence counts.
- `summary.section_kind_counts`: counts for numbered and QMS headings.
- `summary.risk_code_counts`: aggregate structure risk counts.

Section paths are deterministic routing metadata. Numbered headings use label
paths such as `1`, `1/1.1` and `1/1.1/1.1.1`; common QMS headings use
canonical paths such as `objetivo`, `responsabilidades` and `registros`.
Ambiguous headings and hierarchy gaps remain visible as risk codes instead of
being promoted to file-level truth.

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

## Current Result After TASK-027

Run after header/footer and section-tree hardening:

| File | Sections | Header spans | Footer spans | Structure risks |
|------|----------|--------------|--------------|-----------------|
| `pop-o-snvs-010-rev4.pdf` | 25 | 14 | 11 | `ambiguous_section_heading: 1` |
| `dirty/bluesun-blu002-kit-fotovoltaico.pdf` | 25 | 13 | 0 | `ambiguous_section_heading: 1` |
| `dirty/cispar-pop-005-inspecao-concreto.pdf` | 17 | 4 | 0 | `ambiguous_section_heading: 1`, `section_hierarchy_gap: 1` |
| `dirty/hospitalregional-higienizacao-maos-figuras.pdf` | 35 | 18 | 0 | `ambiguous_section_heading: 1` |
| `dirty/ponte-pop-pmpr-fotos.pdf` | 1,471 | 234 | 0 | `ambiguous_section_heading: 1`, `section_hierarchy_gap: 1` |

Summary:

- documents: 5;
- parsed: 5;
- failed: 0;
- split processed: 1;
- section spans: 1,573;
- section paths: 1,573;
- boilerplate spans: `header: 283`, `footer: 11`;
- structure risks: `ambiguous_section_heading: 5`,
  `section_hierarchy_gap: 2`;
- metadata gaps remain: `missing_document_code: 1`, `missing_revision: 1`.

The PMPR stress PDF now keeps section diagnostics through the split-page
fallback by resolving sections from extracted page objects instead of collapsing
the fallback into a single synthetic page.

## Section-Aware Chunk Diagnostics

After TASK-028, the benchmark also records `chunk_diagnostics` per document and
aggregate chunk metrics in `summary`. These diagnostics are derived from parser
section metadata and do not require a `context_bundle.v1` schema change.

Fields:

- `total_chunk_count`: number of chunks generated for the document.
- `section_path_chunk_count`: chunks carrying deterministic `section_path`
  metadata.
- `chunk_kind_counts`: section-derived chunk kind counts.
- `structure_risk_counts`: risk codes carried by chunks, such as
  `section_hierarchy_gap`.

Run after hierarchical industrial chunking:

| File | Chunks | Chunks with section path | Chunk risks |
|------|--------|--------------------------|-------------|
| `pop-o-snvs-010-rev4.pdf` | 27 | 27 | none |
| `dirty/bluesun-blu002-kit-fotovoltaico.pdf` | 25 | 25 | none |
| `dirty/cispar-pop-005-inspecao-concreto.pdf` | 17 | 17 | `section_hierarchy_gap: 9` |
| `dirty/hospitalregional-higienizacao-maos-figuras.pdf` | 35 | 35 | none |
| `dirty/ponte-pop-pmpr-fotos.pdf` | 1,547 | 1,547 | `section_hierarchy_gap: 144` |

Summary:

- chunks: 1,651;
- chunks with section paths: 1,651;
- chunk kinds: `numbered_heading: 1,499`, `qms_heading: 152`;
- chunk structure risks: `section_hierarchy_gap: 153`.

Chunk hashes remain text-only and deterministic. Section path, page span,
chunk kind and structure risk metadata are carried outside the hash so metadata
changes do not rewrite content identity.

## Semantic Candidate Diagnostics

After TASK-029, the benchmark records deterministic first-pass semantic unit
counts. This layer is rule-based only: it does not call an LLM, embeddings,
OCR, vision or an external service.

Fields:

- `semantic_diagnostics.total_candidate_count`: semantic candidates extracted
  from section-aware chunks.
- `semantic_diagnostics.candidate_kind_counts`: counts by candidate kind.
- `summary.semantic_candidate_count`: aggregate candidate count.
- `summary.semantic_candidate_kind_counts`: aggregate kind counts.

Run after technical semantic unit extraction:

| File | Semantic candidates | Candidate kinds |
|------|---------------------|-----------------|
| `pop-o-snvs-010-rev4.pdf` | 71 | `procedure_step: 19`, `requirement: 52` |
| `dirty/bluesun-blu002-kit-fotovoltaico.pdf` | 11 | `procedure_step: 7`, `requirement: 4` |
| `dirty/cispar-pop-005-inspecao-concreto.pdf` | 11 | `procedure_step: 8`, `requirement: 3` |
| `dirty/hospitalregional-higienizacao-maos-figuras.pdf` | 19 | `procedure_step: 5`, `requirement: 14` |
| `dirty/ponte-pop-pmpr-fotos.pdf` | 906 | `procedure_step: 703`, `requirement: 203` |

Summary:

- semantic candidates: 1,018;
- candidate kinds: `procedure_step: 742`, `requirement: 276`.

Candidate evidence carries the source quote, chunk hash, section path and page
span. Broader contradiction detection, knowledge graph persistence and human
review UI remain out of scope.

## Table/Figure Candidate Diagnostics

After TASK-030, the benchmark records conservative parser-visible table and
figure signals. The parser detects text-table lines, checklist rows and
caption/reference text only; it does not reconstruct scanned table cells or
interpret image pixels.

Fields:

- `table_figure_diagnostics.total_candidate_count`: table, checklist, figure
  and visual-risk candidates.
- `table_figure_diagnostics.candidate_kind_counts`: counts by candidate kind.
- `table_figure_diagnostics.risk_code_counts`: visual risk counts when image
  evidence lacks extractable captions.
- `summary.table_figure_candidate_count`: aggregate candidate count.
- `summary.table_figure_candidate_kind_counts`: aggregate kind counts.
- `summary.table_figure_risk_counts`: aggregate visual risk counts.

Run after table and figure understanding:

| File | Table/figure candidates | Candidate kinds |
|------|-------------------------|-----------------|
| `pop-o-snvs-010-rev4.pdf` | 9 | `figure_reference: 9` |
| `dirty/bluesun-blu002-kit-fotovoltaico.pdf` | 13 | `figure_reference: 13` |
| `dirty/cispar-pop-005-inspecao-concreto.pdf` | 0 | none |
| `dirty/hospitalregional-higienizacao-maos-figuras.pdf` | 2 | `figure_reference: 2` |
| `dirty/ponte-pop-pmpr-fotos.pdf` | 229 | `figure_reference: 176`, `text_table: 4`, `visual_risk: 49` |

Summary:

- table/figure candidates: 253;
- candidate kinds: `figure_reference: 200`, `text_table: 4`,
  `visual_risk: 49`;
- visual risk counts: `visual_content_without_caption: 49`.

Pages with embedded images but sparse or missing caption text keep explicit
`visual_content_without_caption` risk codes in page profiles and table/figure
candidate summaries.

## Human Review Packet Diagnostics

After TASK-031, the benchmark records deterministic review packet summaries.
Packets group low-confidence or risky parser diagnostics with evidence and a
suggested human decision. They are backend/parser contract objects only; no new
review UI or automatic approval flow is introduced.

Fields:

- `review_packet_summary.total_packet_count`: packets generated for a document.
- `review_packet_summary.reason_code_counts`: packet counts by reason.
- `review_packet_summary.severity_counts`: packet counts by severity.
- `summary.review_packet_count`: aggregate packet count.
- `summary.review_packet_reason_counts`: aggregate reason-code counts.

Run after human review packets:

| File | Review packets | Reason codes |
|------|----------------|--------------|
| `pop-o-snvs-010-rev4.pdf` | 1 | `ambiguous_section_hierarchy: 1` |
| `dirty/bluesun-blu002-kit-fotovoltaico.pdf` | 1 | `ambiguous_section_hierarchy: 1` |
| `dirty/cispar-pop-005-inspecao-concreto.pdf` | 11 | `ambiguous_section_hierarchy: 11` |
| `dirty/hospitalregional-higienizacao-maos-figuras.pdf` | 1 | `ambiguous_section_hierarchy: 1` |
| `dirty/ponte-pop-pmpr-fotos.pdf` | 180 | `ambiguous_section_hierarchy: 129`, `missing_metadata: 2`, `visual_table_figure_risk: 49` |

Summary:

- review packets: 194;
- reason codes: `ambiguous_section_hierarchy: 143`, `missing_metadata: 2`,
  `visual_table_figure_risk: 49`.

Review packets preserve existing readiness behavior and `context_bundle.v1`
compatibility. Future UI work can consume packet metadata without promoting
uncertain findings to published truth.

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
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_sections.py packages\parsers\tests\test_industrial_structure.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```
