# TASK-028 - Hierarchical Industrial Chunking With Section Paths

Status: completed

## Goal

Use the section tree from TASK-027 to produce industrial-aware chunks that carry
stable section paths, page spans and evidence metadata without changing
`context_bundle.v1`.

## Background

The generic chunker currently splits pages and rough sections, but industrial
documents need chunks that preserve document hierarchy. A rule extracted from
`5.2 Investigacao de causa` should carry that path so later extraction,
review and bundle readiness can explain where evidence came from.

This task depends on TASK-027. It should not begin until section paths and
boilerplate diagnostics are available in parser metadata.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Ensures TASK-027 is complete and keeps chunking scope narrow |
| Task Worker | Adds red chunker tests and implements industrial chunk metadata |
| Reviewer | Reviews ordering, hashing stability and compatibility with existing chunks |
| Approval | Runs parser/chunker tests, smoke benchmark and source-pack compatibility checks |

## Scope

- Add industrial chunk metadata fields such as `section_path`, `section_title`,
  `page_start`, `page_end`, `chunk_kind` and `structure_risk_codes`.
- Prefer section-boundary chunks for industrial PDFs when section diagnostics
  are available.
- Keep existing generic chunker behavior for non-industrial documents.
- Keep chunk hashes deterministic.
- Avoid chunking repeated headers/footers as standalone content chunks.
- Preserve existing chunk indexes and source metadata expectations.
- Extend the benchmark report with section-aware chunk summary metrics.

## Out Of Scope

- OCR.
- Table row extraction.
- Figure interpretation.
- LLM semantic extraction.
- Human review UI.
- Database schema migrations unless a later task explicitly approves them.
- `context_bundle.v2`.
- Hermes, Tri-Memory or agent runtime repair.

## Proposed Files

- Modify: `packages/parsers/src/parsers/chunker.py`
- Modify: `packages/parsers/tests/test_chunker.py`
- Modify: `packages/parsers/src/parsers/industrial_structure.py`
- Modify: `packages/parsers/tests/test_industrial_structure.py`
- Modify: `scripts/industrial/benchmark_dirty_documents.py`
- Modify: `tests/smoke/test_industrial_dirty_benchmark.py`
- Modify: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- Modify: `tasks/TASK-028-hierarchical-industrial-chunking.md`

## Acceptance

- Industrial chunks include stable `section_path` when section diagnostics are
  available.
- Chunks include page-span evidence.
- Header/footer boilerplate does not become standalone chunks.
- Existing generic text/CSV/XLSX chunker tests continue to pass.
- Chunk hashes remain deterministic for unchanged chunk text.
- Benchmark report exposes section-aware chunk counts and risk summaries.
- No `context_bundle.v1` schema change is required.
- No Hermes, Tri-Memory or memory workflow dependency is introduced.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_chunker.py packages\parsers\tests\test_industrial_structure.py -q
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_sections.py packages\parsers\tests\test_pdf.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [ ] Add red tests for `section_path` metadata on industrial chunks.
- [ ] Add red tests for page-span metadata.
- [ ] Add red tests proving generic chunks are unchanged.
- [ ] Add red tests proving boilerplate is not chunked as standalone content.
- [ ] Implement industrial-aware chunk drafts.
- [ ] Preserve deterministic ordering and hashes.
- [ ] Add benchmark chunk diagnostics.
- [ ] Update benchmark documentation.
- [ ] Run the verification target.
- [ ] Record execution evidence in this task file.

## Execution Evidence

Completed on 2026-06-06.

- Added section-aware chunk metadata for `section_path`, section title, page
  span, chunk kind and structure risks.
- Preserved generic chunk behavior and text-only deterministic hashes.
- Extended dirty benchmark with chunk diagnostics and section-path counts.
- Verification included chunker/structure/parser regressions, dirty benchmark
  smoke, real benchmark run, ruff, mypy and secret scan.
