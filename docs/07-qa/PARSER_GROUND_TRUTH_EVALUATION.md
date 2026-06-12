# Parser Ground Truth Evaluation

Status: active

## Purpose

The Parser ground truth evaluator compares parser output against committed
truth expectations. It is the first Parser quality layer that asks whether the
parser found the expected content, not only whether it avoided unsafe
overclaims.

This layer is intentionally parser-first. It runs before the regression ratchet
inside the top quality gate so correctness failures point to `fix_parser`
instead of baseline review.

## Command

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_ground_truth_eval.py
```

To write the deterministic JSON report:

```powershell
uv run --cache-dir .uv-cache python scripts\quality\parser_ground_truth_eval.py --report .run\parser-ground-truth-latest.json
```

The default manifest and input corpus live under:

```text
examples/parser_ground_truth/
```

## Report Shape

The report uses schema version `parser_ground_truth_eval.v1` and includes:

- manifest and benchmark document counts;
- precision, recall and F1;
- missing expected items;
- false positives inside the manifest-scoped item types;
- critical false positives from negative expectations;
- per-document precision and recall;
- structured gate thresholds.

The report has no timestamp and should not include absolute local paths.

## Manifest Shape

Each document entry has a `filename` and an `expected` list. Direct
`expected_code`, `expected_revision` and `expected_processing_mode` fields may
remain in the same manifest because the dirty benchmark already understands
them.

```json
{
  "schema_version": "parser_ground_truth_manifest.v1",
  "documents": [
    {
      "filename": "POP-QA-014_Rev04_vigent.txt",
      "expected_code": "POP-QA-014",
      "expected_revision": "04",
      "expected": [
        {
          "kind": "metadata",
          "type": "document_code",
          "canonical": "POP-QA-014"
        },
        {
          "kind": "semantic",
          "type": "requirement",
          "canonical": "Toda nao conformidade deve ser registrada."
        },
        {
          "kind": "semantic",
          "type": "requirement",
          "canonical": "5.1 Deve registrar incidentes",
          "negative": true
        }
      ]
    }
  ]
}
```

## Item Kinds

Supported expected item kinds:

- `metadata`: `document_code`, `revision`;
- `section`: `section_path`;
- `semantic`: parser semantic candidate kind, such as `requirement` or
  `form_reference`;
- `table_figure`: parser table/figure candidate kind, such as `text_table` or
  `figure_reference`;
- `review_packet`: `reason_code`.

Negative expectations use `"negative": true`. If the parser predicts a
negative item, the report increments `critical_false_positives` and the gate
fails.

## Gates

| Gate | Threshold |
|------|-----------|
| `precision` | `>= 0.85` |
| `recall` | `>= 0.75` |
| `missing_count` | `= 0` |
| `critical_false_positives` | `= 0` |

The `missing_count` gate is stricter than recall. A small corpus should not
silently tolerate a missing expected parser truth item just because the recall
ratio remains above threshold.

## Extension Rules

- Add public, deterministic text fixtures first.
- Use tiny generated fixtures for CI; keep real PDFs local or downloadable in a
  separate approved corpus task.
- Add both positive expectations and negative expectations when expanding a
  parser behavior.
- Keep expectations scoped to parser outputs, not downstream publication.
- Do not add OCR, vision or LLM adjudication to this evaluator.
- Do not commit `.run` reports, private PDFs or absolute local paths.
