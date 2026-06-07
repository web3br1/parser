# TASK-034 - Negative And Adversarial Parser Tests

Status: completed

## Goal

Add parser tests that prove the system refuses unsafe promotions and exposes
fragility-specific risks instead of making claims it cannot support.

## Background

The project currently has strong positive-path parser tests and dirty benchmark
diagnostics. The next quality jump requires negative and adversarial tests:
documents that look tempting to extract from but should not be promoted as
trusted truth.

This task converts fixture-pack expectations into TDD tests. It should make
fragilities visible as red tests before any parser correction is written.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Chooses one fragility at a time and prevents broad parser rewrites |
| Task Worker | Writes failing negative/adversarial tests first, then minimal parser fixes |
| Reviewer | Reviews false-positive protection, evidence grounding and scope control |
| Approval | Runs parser tests, smoke tests, dirty benchmark smoke, lint, type checks and secret scan |

## Scope

- Add tests for metadata overclaim:
  - nested appendix codes must not become file-level `document_code`;
  - ambiguous multi-document files must emit review/risk signals.
- Add tests for semantic overclaim:
  - table-of-contents lines containing requirement words must not become
    semantic requirements;
  - procedural verbs in headers/footers must not become procedure steps.
- Add tests for visual overclaim:
  - figure references without captions must be references or risks, not visual
    understanding claims;
  - sparse visual placeholders must emit review risk.
- Add tests for structure overclaim:
  - hierarchy gaps must remain risk codes;
  - repeated boilerplate must not become body sections.
- Add tests for review noise:
  - related risks should group into bounded packets instead of producing
    unbounded duplicates.

## Out Of Scope

- New benchmark score model.
- New UI.
- OCR or visual model calls.
- LLM adjudication.
- Runtime app changes.
- Hermes, Tri-Memory or agent infrastructure repair.

## Proposed Files

- Create: `packages/parsers/tests/test_industrial_negative_adversarial.py`
- Modify: `packages/parsers/src/parsers/industrial_metadata.py`
- Modify: `packages/parsers/src/parsers/industrial_sections.py`
- Modify: `packages/parsers/src/parsers/industrial_semantics.py`
- Modify: `packages/parsers/src/parsers/industrial_tables.py`
- Modify: `packages/parsers/src/parsers/industrial_review.py`
- Modify: `tests/smoke/test_parser_fragility_fixtures.py`
- Modify: `tasks/TASK-034-negative-adversarial-parser-tests.md`

## Acceptance

- Each implemented behavior starts with a failing test.
- Tests reference committed parser fragility fixtures.
- Negative tests assert what must not be promoted.
- Adversarial tests assert the risk or review packet that should be emitted.
- Parser fixes are minimal and local to the relevant parser module.
- Existing positive-path tests continue to pass.
- Dirty benchmark behavior remains diagnostic rather than overclaiming.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_negative_adversarial.py -q
uv run --cache-dir .uv-cache pytest packages\parsers\tests -q
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_fixtures.py tests\smoke\test_industrial_dirty_benchmark.py -q
uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [x] Add red tests for metadata overclaim.
- [x] Add red tests for semantic overclaim.
- [x] Add red tests for visual overclaim.
- [x] Add red tests for structure overclaim.
- [x] Add red tests for review packet noise.
- [x] Implement minimal parser corrections.
- [x] Run the verification target.
- [x] Record execution evidence in this task file.

## Execution Evidence

Completed on 2026-06-06.

TDD red:

```text
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_negative_adversarial.py -q
6 failed and 4 passed.

Expected red failures:
- ambiguous nested document codes did not emit metadata/review risk.
- Sumario requirement-looking entries with stripped page numbers became requirements.
- explicitly marked boilerplate header text became a semantic candidate.
- placeholder figure text suppressed visual risk.
- section hierarchy review packets duplicated per affected span.
- late split-range hierarchy risk duplicated instead of grouping.
```

TDD green:

```text
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_negative_adversarial.py -q
10 passed in 0.05s.
```

Spec review follow-up:

```text
Added protected green coverage for STEP_RE-shaped header/footer boilerplate
lines. The same strings become procedure_step candidates when unmarked, and
produce no procedure_step candidates when marked as header/footer boilerplate.

uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_negative_adversarial.py -q
11 passed in 0.05s.

No industrial_semantics.py change was needed because the existing
_is_boilerplate_chunk guard already blocks these candidates.
```

Code quality review follow-up:

```text
Added red adversarial coverage for:
- nested POP/IT codes before any TOC delimiter being promoted as file metadata.
- sparse visual profile risks losing ocr_required and sparse_text_with_images.
- split-stress surrogate diagnostics derived from fixture page markers.
- Indice and Table of Contents TOC aliases.

uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_negative_adversarial.py -q
3 failed and 10 passed.

Expected red failures:
- metadata promoted POP 101 as document_code.
- Indice/Table of Contents produced a requirement candidate.
- visual_risk collapsed profile risks to visual_content_without_caption only.

Green:
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_negative_adversarial.py -q
13 passed in 0.05s.

Full parser regression after updating the existing table-risk expectation:
uv run --cache-dir .uv-cache pytest packages\parsers\tests -q
104 passed in 0.49s.
```

Final verification:

```text
uv run --cache-dir .uv-cache pytest packages\parsers\tests\test_industrial_negative_adversarial.py -q
13 passed in 0.05s.

uv run --cache-dir .uv-cache pytest packages\parsers\tests -q
104 passed in 0.49s.

uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_fixtures.py tests\smoke\test_industrial_dirty_benchmark.py -q
11 passed in 0.17s.

uv run --cache-dir .uv-cache ruff check packages\parsers scripts tests
All checks passed.

uv run --cache-dir .uv-cache mypy --ignore-missing-imports -p parsers
Success: no issues found in 16 source files.

uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
exit 0 with only SSL_CERT_DIR warnings.
```
