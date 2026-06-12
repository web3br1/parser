# TASK-024 - Industrial Dirty Document Benchmark

Status: implemented; benchmark executed locally on 2026-06-03

## Goal

Compare the industrial parser performance across real technical documents with
clean, semi-clean and dirty layouts, including documents with images, figures,
tables, dense forms and page-count stress.

## Background

TASK-023 added the first industrial/QMS parser slice: deterministic metadata
candidates, structure hints, industrial schema types and readiness blockers. The
current synthetic fixtures prove the contract, but they do not measure behavior
on real noisy PDFs.

This task turns the downloaded real-document set into a repeatable benchmark so
we can track extraction quality, regressions and the next parser gaps.

## Real Corpus

The current local comparison set lives under `.run/industrial-real` and should
be treated as disposable benchmark input. Do not commit the PDF binaries.
Instead, preserve source URLs and add a downloader/manifest in the implementation
if the corpus becomes part of CI or recurring QA.

| Document | Source URL | Purpose |
|----------|------------|---------|
| `pop-o-snvs-010-rev4.pdf` | `https://www.gov.br/anvisa/pt-br/centraisdeconteudo/publicacoes/certificacao-e-fiscalizacao/compilado-procedimentos-SNVS/010/pop-o-snvs-010-rev-3-1-gerenciamento-de-documentos-do-snvs.pdf` | Clean official POP baseline with revision, vigency, sections and 14 pages |
| `bluesun-blu002-kit-fotovoltaico.pdf` | `https://cdn.bluesundobrasil.com.br/datasheets/a/877241.pdf` | Industrial POP with diagrams, checklists, annexes and 23 embedded images |
| `cispar-pop-005-inspecao-concreto.pdf` | `https://www.cispar.pr.gov.br/uploads/pagina/arquivos/POP-05-Roteiro-Para-Inspecao-de-Estruturas-de-Concreto.pdf` | Dense technical form/inspection procedure with fields and image references |
| `hospitalregional-higienizacao-maos-figuras.pdf` | `https://www.hospitalregional.ms.gov.br/wp-content/uploads/2023/11/PTC.DEPQI-SCIRAS.001-Higienizacao-das-Maos.pdf` | Protocol with many figures, long textual body and complex headers |
| `ponte-pop-pmpr-fotos.pdf` | `https://ponte.org/wp-content/uploads/2021/05/POP-3a-edicao-revisto-e-ampliado.pdf` | Dirty stress case: very large PDF, hundreds of pages and hundreds of images |

## Baseline Observations

Measured on 2026-06-03 with the current TASK-023 implementation:

| Document | Pages | Images | Extracted chars | Parser result | Current gap signal |
|----------|-------|--------|-----------------|---------------|--------------------|
| `pop-o-snvs-010-rev4.pdf` | 14 | 14 | 25,679 | parsed | misses `POP-O-SNVS-010` document code |
| `bluesun-blu002-kit-fotovoltaico.pdf` | 13 | 23 | 14,932 | parsed | misses compact code `BLU002` |
| `cispar-pop-005-inspecao-concreto.pdf` | 4 | 4 | 7,019 | parsed | misses spaced code `POP 005` |
| `hospitalregional-higienizacao-maos-figuras.pdf` | 25 | 83 | 39,134 | parsed | misses protocol code and revision |
| `ponte-pop-pmpr-fotos.pdf` | 374 | 306 | 0 | `pages_exceeded` | expected stress blocker under current 200-page limit |

## Scope

- Create a repeatable benchmark harness for local dirty industrial PDFs.
- Record per-document parser metrics:
  - file size;
  - page count;
  - embedded image count;
  - extracted character count;
  - parser error;
  - elapsed parse time;
  - deterministic metadata candidate;
  - gap codes;
  - structure hint count.
- Compare real documents against synthetic fixtures from
  `examples/industrial_qms`.
- Capture expected parser limitations without hiding failures.
- Produce a JSON report under `.run/industrial-real/benchmark-*.json`.
- Add unit/smoke tests for the harness using tiny synthetic fixtures, not the
  downloaded PDFs.

## Out Of Scope

- Committing real PDF binaries.
- OCR implementation.
- Visual/layout extraction beyond counting embedded images.
- Changing the `context_bundle.v1` contract.
- Full API ingest, review and publish flow.
- Cloud CI download of third-party PDFs unless explicitly approved in a
  separate task.

## Proposed Files

- Create: `scripts/industrial/benchmark_dirty_documents.py`
  - CLI for benchmark input directory, optional manifest and JSON output.
- Create: `tests/smoke/test_industrial_dirty_benchmark.py`
  - Tests the benchmark harness with generated small PDFs or existing tiny parser
    fixtures.
- Create: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
  - Documents corpus, metrics, interpretation and known baseline gaps.
- Modify: `tasks/TASK-024-industrial-dirty-document-benchmark.md`
  - Update status and final evidence after implementation.

## Acceptance

- Benchmark can run locally against `.run/industrial-real` without publishing
  data or requiring API/Supabase.
- Benchmark output is deterministic enough for comparison:
  - stable document IDs;
  - stable metric names;
  - stable JSON shape;
  - no absolute private paths in committed reports/docs.
- Report includes all five real documents when present.
- The huge PMPR PDF is split across two page-range workers when the single
  parser reports `pages_exceeded`.
- Current known misses are recorded as benchmark findings:
  - `POP-O-SNVS-010`;
  - `BLU002`;
  - `POP 005`;
  - `PTC.DEPQI-SCIRAS.001`.
- Tests cover parser success, parser failure and metadata-gap reporting.
- Documentation explains that PDFs are local/downloaded inputs and should not be
  committed.

## Verification Target

```powershell
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache ruff check scripts tests
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [x] Add failing tests for the benchmark JSON shape.
- [x] Add failing tests for parser-error reporting.
- [x] Implement the CLI harness.
- [x] Run the harness against a tiny test fixture directory.
- [x] Run the harness against `.run\industrial-real`.
- [x] Save benchmark output under `.run\industrial-real\benchmark-latest.json`.
- [x] Document corpus sources, metrics and current known parser misses.
- [x] Run verification target.
- [x] Decide follow-up task for industrial document-code pattern expansion.

## Execution Evidence

Benchmark report:

```text
.run\industrial-real\benchmark-latest.json
```

Observed summary:

- documents: 5;
- parsed: 5;
- failed: 0;
- split processed: 1;
- total pages: 430;
- total embedded images: 430;
- total extracted characters: 586,764;
- parser errors: none;
- metadata gaps: `missing_document_code: 5`, `missing_revision: 2`.

Follow-up decision:

- Create a follow-up parser task to expand industrial document-code patterns for
  `POP-O-SNVS-010`, `BLU002`, `POP 005` and `PTC.DEPQI-SCIRAS.001`.
