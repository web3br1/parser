# Parser Fixture Factory

Status: active fixture pack
Date: 2026-06-06

## Purpose

The parser fragility fixture pack turns cataloged risks into deterministic,
minimal text documents. Each fixture isolates one fragility from
`PARSER_FRAGILITY_CATALOG.md` so future red tests can reproduce a failure
without private PDFs, `.run` artifacts, OCR, image generation or benchmark
scoring.

## Manifest Shape

The fixture pack lives under `examples/parser_fragility/`.
`manifest.json` is the source of truth and contains:

| field | meaning |
|---|---|
| `fixture_pack_id` | Stable pack identifier. Current value: `parser_fragility.v1`. |
| `language` | Fixture language. Current value: `pt-BR`. |
| `documents` | List of fixture records. |
| `filename` | Text file name relative to the fixture directory. |
| `scenario` | Stable scenario name used by tests. |
| `fragility_ids` | One or more IDs from the parser fragility catalog. |
| `fixture_kind` | Current value: `synthetic_text`. |
| `positive_expectations` | Risk shape the fixture should expose. |
| `negative_expectations` | Unsafe promotions or claims that future tests must block. |
| `invariant_expectations` | Determinism and size constraints for smoke tests. |

Negative expectation keys should use `must_not_promote` or `must_not_claim`
style names. This keeps the fixture connected to adversarial assertions rather
than generic quality goals.

## Fixture Kinds

`synthetic_text` fixtures are small text artifacts written for TDD. They are
not dirty-document benchmarks and do not prove production parser performance.
They should be readable enough that a reviewer can identify the fragility by
inspection.

Use one fixture for one dominant risk. If a later parser red test needs a
different shape, add a new fixture or a new scenario instead of expanding a
minimal fixture into a broad corpus sample.

## Promotion To PDF

Promote a fixture from synthetic text to PDF only when the fragility depends on
properties text cannot represent:

- page image presence or absence;
- extractable text layer boundaries;
- OCR routing;
- page coordinates, captions, tables or visual layout;
- split behavior that depends on actual page count limits.

Promotion should create a separate scoped task. The PDF should remain generated
or otherwise deterministic, and the manifest should keep the catalog ID,
negative expectations and promotion reason visible.

## How Red Tests Use Fixtures

Future parser tests should load a fixture by `scenario` or `filename`, run the
narrow parser layer under test and assert the manifest expectations. Positive
expectations describe what risk should be visible. Negative expectations define
what must not be promoted or claimed. Invariants keep the fixture compact and
stable for smoke tests.

## Regression Ratchet

The accepted fixture-quality baseline lives at
`examples/parser_fragility/baselines/parser-fragility-baseline.v1.json`.
It stores only stable counts and schema names: metadata expectation hits,
negative expectation passes, adversarial risk emissions, invariant pass counts,
review packet reason counts and the dirty-benchmark schema version.

Run the ratchet with:

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_regression_ratchet.py
```

The script uses path-specific comparison policy. Metadata hits, negative
expectation passes and concrete invariant pass counts improve upward and
regress downward. Review-packet reason counts and adversarial risk emissions
are treated as burden/noise signals, so increases are regressions and decreases
are improvements. Schema and fixture-pack identity must match exactly.
Intentional baseline updates must use a reason:

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_regression_ratchet.py --update-baseline --reason "Explain accepted parser-quality change"
```

The optional dirty corpus remains local. If `.run/industrial-real` or its
latest benchmark summary is absent, the ratchet marks that comparison as
`skipped`; absence is not reported as a pass.
