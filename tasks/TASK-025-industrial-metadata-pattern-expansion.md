# TASK-025 - Industrial Metadata Pattern Expansion

Status: implemented; benchmark executed locally on 2026-06-03

## Goal

Improve deterministic industrial metadata quality on the real dirty-document
benchmark by expanding document-code recognition beyond the synthetic
`POP-QA-014` style.

## Background

TASK-024 showed that the parser was operationally robust on five real PDFs, but
it missed every expected document code:

- `POP-O-SNVS-010`;
- `BLU002`;
- `POP 005`;
- `PTC.DEPQI-SCIRAS.001`;
- no safe file-level code for the PMPR stress document.

This task addresses the deterministic metadata layer only. It does not add OCR,
visual layout reasoning, local LLM extraction or changes to `context_bundle.v1`.

## SDD Roles

- Orchestrator: define acceptance from the benchmark misses.
- Task worker: add red tests for real metadata patterns.
- Reviewer: inspect false-positive risk and benchmark deltas.
- Approval: confirm tests, benchmark and docs are coherent.

## Scope

- Recognize multi-segment controlled codes such as `POP-O-SNVS-010`.
- Recognize compact codes near code headers or strong filenames, such as
  `BLU002`.
- Recognize spaced POP codes such as `POP 005`.
- Recognize dotted protocol codes with dash segments, such as
  `PTC.DEPQI-SCIRAS.001`.
- Read stacked labels for code/revision values in dirty PDF text extraction.
- Treat explicit protocol version labels such as `Versao n.`/`Versao no.` as
  revision metadata.
- Keep compact-code extraction conservative to avoid table-of-contents section
  IDs becoming file-level metadata.
- Preserve existing behavior for synthetic QMS fixtures and header-code
  priority over referenced form codes.

## Out Of Scope

- OCR.
- Image captioning or figure interpretation.
- Semantic requirement/responsibility extraction.
- Full review/publish flow.
- Committing real PDF binaries or `.run` artifacts.

## Files

- Modified: `packages/parsers/src/parsers/industrial_metadata.py`
- Modified: `packages/parsers/tests/test_industrial_metadata.py`
- Modified: `scripts/industrial/benchmark_dirty_documents.py`
- Modified: `tests/smoke/test_industrial_dirty_benchmark.py`
- Modified: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`

## Acceptance

- Unit tests cover all four real document-code formats.
- `missing_document_code` falls from 5 to 1 on the real benchmark.
- Known expected-code misses are zero for:
  - `POP-O-SNVS-010`;
  - `BLU002`;
  - `POP 005`;
  - `PTC.DEPQI-SCIRAS.001`.
- PMPR remains a gap instead of accepting `POP 101` from the table of contents.
- BLU002 does not populate `owner_area` from a table row by accident.
- Benchmark still parses 5/5 documents and uses two workers for the PMPR
  page-count fallback.

## Execution Evidence

Red test before implementation:

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_metadata.py -q
```

Observed first red result:

- 4 failed, 5 passed from worker test set;
- 2 additional red regressions added for PMPR false positive and BLU owner area.

Current benchmark summary:

```text
documents: 5
parsed: 5
failed: 0
split processed: 1
metadata gaps: missing_document_code: 1, missing_revision: 1
known findings: none
```

Current per-document metadata:

| Document | Code | Revision | Gaps |
|----------|------|----------|------|
| `pop-o-snvs-010-rev4.pdf` | `POP-O-SNVS-010` | `04` | none |
| `bluesun-blu002-kit-fotovoltaico.pdf` | `BLU002` | `00` | none |
| `cispar-pop-005-inspecao-concreto.pdf` | `POP 005` | `00` | none |
| `hospitalregional-higienizacao-maos-figuras.pdf` | `PTC.DEPQI-SCIRAS.001` | `1.0.0` | none |
| `ponte-pop-pmpr-fotos.pdf` | missing | missing | `missing_document_code`, `missing_revision` |

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_metadata.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Remaining Gaps

- Broader revision/version policy still needs semantic validation. This task only
  accepts explicit controlled-document version labels such as `Versao n.` and
  does not infer revision from dates or next-review fields.
- PMPR is a book-like collection of many POP sections, so file-level metadata
  needs collection/document-family handling before a safe code can be assigned.
- Semantic quality still depends on hierarchical chunking, layout evidence and
  specialized/local model evaluation in later tasks.
