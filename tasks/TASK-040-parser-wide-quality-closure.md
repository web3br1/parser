# TASK-040 - Parser-Wide Quality Closure

Status: planned

## Goal

Implement a parser-wide quality closure slice that proves parser outputs are
calibrated across parse, truth, review, publication and release contracts.

## Background

TASK-024 through TASK-031 built the industrial dirty-document benchmark and
parser diagnostics. TASK-032 through TASK-038 built the quality ladder with
fixtures, adversarial tests, invariants, ratchets, a top-level quality gate and
ground truth evaluation. TASK-039 then defined the Parser Architecture Spine.

The remaining quality gap is vertical: every parser family needs a common way to
prove that evidence-backed candidates are not promoted into unsafe truth.

## Scope

- Add parser-wide quality profile signals.
- Detect collection/document-family style artifacts in a generic way.
- Preserve nested identifiers as candidates/evidence while blocking unsafe
  file-level metadata promotion.
- Extend parser ground truth to evaluate quality-profile and nested-identifier
  expectations.
- Generate review packets for unresolved parser-wide quality risks.
- Prove unresolved parser quality gaps block context bundle readiness.
- Preserve existing `context_bundle.v1` compatibility.

## Out Of Scope

- OCR or vision.
- LLM adjudication.
- Review UI.
- Database migrations.
- Runtime importer changes.
- New bundle schema version.
- Committing dirty real PDFs or `.run` artifacts.

## Proposed Files

- Create: `packages/parsers/src/parsers/quality_profile.py`
- Create: `packages/parsers/tests/test_quality_profile.py`
- Modify: `packages/parsers/src/parsers/industrial_metadata.py`
- Modify: `packages/parsers/src/parsers/industrial_review.py`
- Modify: `packages/parsers/tests/test_industrial_metadata.py`
- Modify: `packages/parsers/tests/test_industrial_review.py`
- Modify: `scripts/industrial/benchmark_dirty_documents.py`
- Modify: `scripts/quality/parser_ground_truth_eval.py`
- Modify: `tests/smoke/test_parser_ground_truth_eval.py`
- Modify: `examples/parser_ground_truth/manifest.json`
- Add fixtures under `examples/parser_ground_truth/`
- Modify: `tests/api/test_context_bundle.py`
- Modify: `docs/07-qa/PARSER_GROUND_TRUTH_EVALUATION.md`
- Modify: `docs/03-pipeline/INDUSTRIAL_DIRTY_DOCUMENT_BENCHMARK.md`
- Modify: `tasks/TASK-040-parser-wide-quality-closure.md`

## Acceptance

- Generic quality profile detects document-family candidates and nested
  identifiers from sanitized fixtures.
- Industrial metadata still refuses unsafe file-level code promotion for nested
  collections.
- Internal identifiers are available as evidence-backed candidates.
- Ground truth evaluator supports `quality_profile` and `nested_identifier`
  expectation kinds.
- Negative ground truth catches unsafe file-level metadata promotion.
- Review packets include `document_family_requires_review` with representative
  evidence.
- Context bundle readiness blocks unresolved parser quality collection gaps.
- Top-level Parser quality gate passes.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_quality_profile.py -q
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_metadata.py packages\parsers\tests\test_industrial_review.py -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_ground_truth_eval.py tests\api\test_context_bundle.py -q
uv run --cache-dir .uv-cache python scripts\quality\parser_ground_truth_eval.py
uv run --cache-dir .uv-cache python scripts\quality\parser_quality_gate.py
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [ ] Add parser-wide quality profile tests.
- [ ] Implement parser-wide quality profile.
- [ ] Extend industrial metadata/review integration.
- [ ] Extend ground truth fixtures and evaluator.
- [ ] Add context bundle readiness coverage.
- [ ] Update docs.
- [ ] Run verification target.
- [ ] Record execution evidence.

