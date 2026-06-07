# TASK-031 - Human Review Packets For Industrial Diagnostics

Status: completed

## Goal

Package low-confidence industrial parser diagnostics into human-review-ready
packets with evidence, section paths, page diagnostics and blocker reasons.

## Background

After TASK-027 through TASK-030, the parser should expose structured metadata,
section paths, semantic unit candidates and table/figure risk signals. The next
product gap is review ergonomics: uncertain industrial findings should be
grouped into review packets that explain what failed, where the evidence lives
and what a human should decide.

This task does not build a new UI. It creates backend/parser packet structures
and tests so the existing review flow can later consume them.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Keeps this as review packet contract work, not a UI rewrite |
| Task Worker | Adds red tests for packet shape, blocker grouping and evidence fields |
| Reviewer | Reviews packet clarity, privacy, evidence completeness and readiness compatibility |
| Approval | Runs parser, API/context bundle and smoke gates |

## Scope

- Define industrial review packet objects for:
  - missing/ambiguous document metadata;
  - ambiguous section hierarchy;
  - low-confidence semantic units;
  - visual/table/figure risk;
  - revision-family conflicts.
- Attach evidence quotes, page numbers, section paths and risk codes.
- Group related findings so one document does not create noisy duplicate review
  items.
- Add packet summaries to the dirty-document benchmark report.
- Preserve existing readiness blockers and context bundle compatibility.

## Out Of Scope

- New human review UI.
- Automatic approval or rejection.
- LLM adjudication.
- OCR.
- Knowledge graph persistence.
- `context_bundle.v2`.
- Hermes, Tri-Memory or agent runtime repair.

## Proposed Files

- Create: `packages/parsers/src/parsers/industrial_review.py`
- Create: `packages/parsers/tests/test_industrial_review.py`
- Modify: `packages/parsers/src/parsers/industrial_structure.py`
- Modify: `packages/parsers/tests/test_industrial_structure.py`
- Modify: `tests/api/test_context_bundle.py`
- Modify: `scripts/industrial/benchmark_dirty_documents.py`
- Modify: `tests/smoke/test_industrial_dirty_benchmark.py`
- Modify: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- Modify: `tasks/TASK-031-human-review-packets-industrial-diagnostics.md`

## Acceptance

- Review packets include stable `packet_id`, `reason_code`, severity, evidence
  and suggested human decision.
- Missing document metadata and revision conflicts produce review packets.
- Ambiguous sections produce review packets without blocking clean documents.
- Low-confidence semantic units can be grouped by section path.
- Table/figure risk can produce review packets when text evidence is
  insufficient.
- Benchmark report includes review packet counts by reason code.
- Existing context bundle readiness blockers remain compatible.
- No automatic memory approval or external agent infrastructure is introduced.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_review.py packages\parsers\tests\test_industrial_structure.py -q
uv run --cache-dir .uv-cache pytest tests\api\test_context_bundle.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache python scripts\industrial\benchmark_dirty_documents.py --input-dir .run\industrial-real --output .run\industrial-real\benchmark-latest.json
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [ ] Add red tests for missing metadata review packets.
- [ ] Add red tests for revision conflict packets.
- [ ] Add red tests for ambiguous section packets.
- [ ] Add red tests for low-confidence semantic unit packets.
- [ ] Add red tests for table/figure risk packets.
- [ ] Implement deterministic packet creation.
- [ ] Add benchmark review packet summaries.
- [ ] Update benchmark documentation.
- [ ] Run the verification target.
- [ ] Record execution evidence in this task file.

## Execution Evidence

Completed on 2026-06-06.

- Added deterministic industrial review packets for missing metadata, revision
  conflicts, ambiguous section hierarchy, low-confidence semantic units and
  visual/table/figure risks.
- Packets carry stable IDs, reason codes, severity, evidence and suggested
  human decisions.
- Extended dirty benchmark with review packet summaries while preserving
  context bundle compatibility.
- Verification included review/structure tests, context bundle tests, dirty
  benchmark smoke, real benchmark run, ruff, mypy and secret scan.
