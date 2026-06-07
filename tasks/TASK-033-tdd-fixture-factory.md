# TASK-033 - TDD Fixture Factory

Status: completed

## Goal

Create a deterministic fixture factory that turns cataloged fragilities into
minimal documents used by red tests.

## Background

Benchmarks based only on real dirty PDFs are useful but too heavy for TDD. The
quality program needs small fixtures that reproduce one fragility at a time:
metadata ambiguity, section drift, table-of-contents contamination, visual
overclaim and evidence drift.

This task builds the fixture layer beneath benchmarks. The output should let a
Task Worker write a failing test for a fragility without depending on private
PDFs under `.run`.

## SDD Roles

| Role | Responsibility |
|------|----------------|
| Orchestrator | Ensures each fixture exists to expose a named fragility, not to pad corpus size |
| Task Worker | Builds deterministic fixture files, manifest entries and fixture validation tests |
| Reviewer | Checks that fixtures are minimal, readable and tied to catalog IDs |
| Approval | Runs fixture smoke tests, parser fixture tests and secret scan |

## Scope

- Create a committed parser fragility fixture pack.
- Define a fixture manifest with:
  - `fixture_pack_id`;
  - `language`;
  - `documents`;
  - `filename`;
  - `scenario`;
  - `fragility_ids`;
  - `fixture_kind`;
  - `positive_expectations`;
  - `negative_expectations`;
  - `invariant_expectations`.
- Add minimal text fixtures for:
  - multi-document appendix code ambiguity;
  - table-of-contents requirement contamination;
  - repeated header/footer contamination;
  - figure reference without visual evidence;
  - sparse image placeholder requiring review risk;
  - section hierarchy gap;
  - evidence quote boundary drift;
  - split-document stress surrogate.
- Keep fixtures deterministic and small enough for unit/smoke tests.
- Document when a fixture should be promoted from synthetic text to PDF.

## Out Of Scope

- Real dirty PDF downloads.
- OCR or image-generation pipelines.
- Parser behavior changes.
- Benchmark scoring.
- CI enforcement beyond fixture validation.
- Hermes, Tri-Memory or agent infrastructure repair.

## Proposed Files

- Create: `examples/parser_fragility/manifest.json`
- Create: `examples/parser_fragility/multi_document_appendix_codes.txt`
- Create: `examples/parser_fragility/toc_requirement_words.txt`
- Create: `examples/parser_fragility/repeated_boilerplate_sections.txt`
- Create: `examples/parser_fragility/figure_reference_without_caption.txt`
- Create: `examples/parser_fragility/sparse_visual_placeholder.txt`
- Create: `examples/parser_fragility/section_hierarchy_gap.txt`
- Create: `examples/parser_fragility/evidence_boundary_drift.txt`
- Create: `examples/parser_fragility/split_stress_surrogate.txt`
- Create: `docs/07-qa/PARSER_FIXTURE_FACTORY.md`
- Create: `tests/smoke/test_parser_fragility_fixtures.py`
- Modify: `tasks/TASK-033-tdd-fixture-factory.md`

## Acceptance

- Fixture manifest exists and validates.
- Every fixture is linked to one or more fragility IDs from TASK-032.
- Every fixture has at least one positive or negative expectation.
- Negative expectations use explicit `must_not_promote` or `must_not_claim`
  style checks.
- Fixtures are committed text artifacts unless the scenario requires another
  format.
- Fixture validation proves referenced files exist and expected fields are
  present.

## Verification Target

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_fixtures.py -q
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

## Execution Checklist

- [x] Add a red smoke test for fixture manifest schema.
- [x] Add a red smoke test that each manifest file exists.
- [x] Create the fixture manifest.
- [x] Create the first eight minimal fragility fixtures.
- [x] Add fixture factory documentation.
- [x] Run the verification target.
- [x] Record execution evidence in this task file.

## Execution Evidence

Completed on 2026-06-06.

TDD red:

```text
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_fixtures.py -q
4 failed because examples/parser_fragility/manifest.json and docs/07-qa/PARSER_FIXTURE_FACTORY.md were missing.
```

TDD green:

```text
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_fixtures.py -q
4 passed in 0.02s.
```

Final verification:

```text
uv run --cache-dir .uv-cache pytest tests\smoke\test_parser_fragility_fixtures.py -q
4 passed in 0.02s.

uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
exit 0 with only SSL_CERT_DIR warnings.
```
