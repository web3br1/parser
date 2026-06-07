# TASK-029 - Technical Semantic Unit Extraction With Evidence

Status: completed

## Goal

Extract deterministic industrial semantic units from section-aware chunks:
requirements, responsibilities, records, forms, equipment references and
procedure steps with explicit evidence.

## Background

TASK-027 and TASK-028 should make industrial text structurally navigable. The
next product step is to turn that structure into useful candidate facts and
rules without calling a model. This first slice should be deterministic and
auditable: each extracted unit needs a type, normalized payload, confidence,
section path and source quote.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Limits the scope to deterministic first-pass extraction |
| Task Worker | Adds red tests for each semantic unit type and implements extraction helpers |
| Reviewer | Reviews evidence quality, false positives and readiness blocker compatibility |
| Approval | Runs parser, context bundle and benchmark verification gates |

## Scope

- Extract industrial requirement candidates from normative language such as
  `deve`, `devem`, `obrigatorio`, `proibido`, `necessario`.
- Extract responsibility candidates from role/action patterns.
- Extract record/form references from labels such as `Registro`, `Formulario`,
  `Anexo`, `FR`, `FOR`, `Lista de verificacao`.
- Extract procedure-step candidates from numbered or imperative procedural
  lines.
- Attach evidence quotes, section paths and page spans.
- Keep candidates deterministic and conservative.
- Add benchmark summary counts for semantic unit candidates.

## Out Of Scope

- LLM extraction.
- Semantic contradiction detection.
- Embedding similarity.
- Knowledge graph persistence.
- Human review UI.
- New bundle schema version.
- Table/figure extraction beyond simple text references.
- Hermes, Tri-Memory or agent runtime repair.

## Proposed Files

- Create: `packages/parsers/src/parsers/industrial_semantics.py`
- Create: `packages/parsers/tests/test_industrial_semantics.py`
- Modify: `packages/parsers/src/parsers/industrial_structure.py`
- Modify: `packages/parsers/tests/test_industrial_structure.py`
- Modify: `scripts/industrial/benchmark_dirty_documents.py`
- Modify: `tests/smoke/test_industrial_dirty_benchmark.py`
- Modify: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- Modify: `tasks/TASK-029-technical-semantic-unit-extraction.md`

## Acceptance

- Requirement candidates include quote, normalized text, section path and
  confidence.
- Responsibility candidates include role/action evidence and avoid promoting
  arbitrary nouns to roles.
- Record/form candidates include identifier/name evidence and avoid table of
  contents false positives.
- Procedure-step candidates preserve ordering within a section.
- Candidate extraction is deterministic and does not call external models.
- Benchmark report includes semantic unit candidate counts.
- Existing TASK-025/TASK-026/TASK-028 behavior does not regress.
- No Hermes, Tri-Memory or memory workflow dependency is introduced.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_semantics.py -q
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_metadata.py packages\parsers\tests\test_industrial_structure.py packages\parsers\tests\test_chunker.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py tests\api\test_context_bundle.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [ ] Add red tests for requirement extraction.
- [ ] Add red tests for responsibility extraction.
- [ ] Add red tests for record/form extraction.
- [ ] Add red tests for ordered procedure-step extraction.
- [ ] Add false-positive regression tests.
- [ ] Implement deterministic semantic extraction helpers.
- [ ] Wire semantic summary into benchmark output.
- [ ] Update benchmark documentation.
- [ ] Run the verification target.
- [ ] Record execution evidence in this task file.

## Execution Evidence

Completed on 2026-06-06.

- Added deterministic semantic candidates for requirements,
  responsibilities, record/form/annex references, equipment references and
  ordered procedure steps.
- Candidates carry evidence quotes, section paths, page spans, confidence and
  deterministic IDs without model calls.
- Extended dirty benchmark with semantic candidate summaries.
- Verification included semantic tests, parser/chunker regressions, dirty
  benchmark smoke, context bundle compatibility, real benchmark run, ruff, mypy
  and secret scan.
